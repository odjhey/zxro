from pathlib import Path

from zxro.contract import Work
from zxro.errors import UnsafeStateError, ValidationError
from zxro.ids import validate_id
from .home import check_owned_mode
from .ioutil import atomic_create, atomic_replace, list_records, mutation, read_json


class LocalWorkStore:
    def __init__(self, home: Path, registry):
        self.home, self.registry = home, registry

    def create(self, id, watchtower_id):
        id, watchtower_id = validate_id(id, "work id"), validate_id(watchtower_id, "watchtower id")
        record = Work(id, watchtower_id, "open")
        with mutation(self.home):
            self.registry.get(watchtower_id)
            atomic_create(self.home / "work" / f"{id}.json", record.to_dict())
        return record

    def get(self, id):
        id = validate_id(id, "work id")
        record = self._decode(read_json(self.home / "work" / f"{id}.json"))
        try:
            self.registry.get(record.watchtower_id)
        except Exception as exc:
            raise UnsafeStateError(f"invalid work ownership: {exc}") from exc
        return record

    def list(self, watchtower_id=None, state=None):
        if watchtower_id is not None:
            validate_id(watchtower_id, "watchtower id")
        if state is not None and state not in ("open", "closed"):
            raise ValidationError(f"invalid work state: {state!r}")
        directory = self.home / "work"
        if self.home.exists() or self.home.is_symlink():
            check_owned_mode(self.home, directory=True)
        if not directory.exists() and not directory.is_symlink():
            return []
        records = [self._decode(item) for item in list_records(directory)]
        for record in records:
            try:
                self.registry.get(record.watchtower_id)
            except Exception as exc:
                raise UnsafeStateError(f"invalid work ownership: {exc}") from exc
        return sorted((item for item in records if (watchtower_id is None or item.watchtower_id == watchtower_id) and (state is None or item.state == state)), key=lambda item: item.id)

    def close(self, id):
        id = validate_id(id, "work id")
        with mutation(self.home):
            current = self.get(id)
            if current.state == "closed":
                return current
            closed = Work(current.id, current.watchtower_id, "closed")
            atomic_replace(self.home / "work" / f"{id}.json", closed.to_dict())
            return closed

    @staticmethod
    def _decode(data):
        if set(data) != {"id", "watchtower_id", "state"} or not all(isinstance(data.get(key), str) for key in data) or data.get("state") not in ("open", "closed"):
            raise UnsafeStateError("invalid work record schema")
        try:
            validate_id(data["id"], "work id"); validate_id(data["watchtower_id"], "watchtower id")
        except Exception as exc:
            raise UnsafeStateError(f"invalid work record: {exc}") from exc
        return Work(**data)
