from pathlib import Path

from zxro.contract import Work
from zxro.errors import NotFoundError, UnsafeStateError, ValidationError
from zxro.ids import validate_id
from zxro.metadata import validate_metadata, validate_name, validate_namespace
from .ioutil import atomic_create, atomic_replace, list_records, mutation, read_json, reading


class LocalWorkStore:
    def __init__(self, home: Path, registry):
        self.home, self.registry = home, registry

    def create(self, id, watchtower_id):
        id, watchtower_id = validate_id(id, "work id"), validate_id(watchtower_id, "watchtower id")
        self.registry.get(watchtower_id)
        record = Work(id, watchtower_id, "open")
        with mutation(self.home) as access:
            self.registry.get_from(access, watchtower_id)
            atomic_create(access, "work", f"{id}.json", record.to_dict())
        return record

    def get(self, id):
        id = validate_id(id, "work id")
        with reading(self.home) as access:
            return self.get_from(access, id)

    def get_from(self, access, id):
        record = self._decode(read_json(access, "work", f"{id}.json"))
        try:
            self.registry.get_from(access, record.watchtower_id)
        except Exception as exc:
            raise UnsafeStateError(f"invalid work ownership: {exc}") from exc
        return record

    def list(self, watchtower_id=None, state=None):
        if watchtower_id is not None:
            validate_id(watchtower_id, "watchtower id")
        if state is not None and state not in ("open", "closed"):
            raise ValidationError(f"invalid work state: {state!r}")
        try:
            with reading(self.home) as access:
                records = [self._decode(item) for item in list_records(access, "work")]
                for record in records:
                    try:
                        self.registry.get_from(access, record.watchtower_id)
                    except Exception as exc:
                        raise UnsafeStateError(f"invalid work ownership: {exc}") from exc
        except NotFoundError:
            return []
        return sorted((item for item in records if (watchtower_id is None or item.watchtower_id == watchtower_id) and (state is None or item.state == state)), key=lambda item: item.id)

    def close(self, id):
        id = validate_id(id, "work id")
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            if current.state == "closed":
                return current
            closed = Work(current.id, current.watchtower_id, "closed", current.metadata)
            atomic_replace(access, "work", f"{id}.json", closed.to_dict())
            return closed

    def set_metadata(self, id, namespace, payload):
        id = validate_id(id, "work id")
        payload = validate_namespace(namespace, payload)
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            metadata = dict(current.metadata or {})
            metadata[namespace] = payload
            metadata = validate_metadata(metadata)
            updated = Work(current.id, current.watchtower_id, current.state, metadata)
            atomic_replace(access, "work", f"{id}.json", updated.to_dict())
            return updated

    def unset_metadata(self, id, namespace):
        id = validate_id(id, "work id")
        validate_name(namespace, "metadata namespace")
        if namespace == "zxro":
            raise ValidationError(f"reserved metadata namespace: {namespace}")
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            if not current.metadata or namespace not in current.metadata:
                return current
            metadata = dict(current.metadata)
            del metadata[namespace]
            updated = Work(current.id, current.watchtower_id, current.state, metadata or None)
            atomic_replace(access, "work", f"{id}.json", updated.to_dict())
            return updated

    @staticmethod
    def _decode(data):
        if not {"id", "watchtower_id", "state"} <= set(data) or set(data) - {"id", "watchtower_id", "state", "metadata"} or not all(isinstance(data.get(key), str) for key in ("id", "watchtower_id", "state")) or data.get("state") not in ("open", "closed") or data.get("metadata", {}) is None:
            raise UnsafeStateError("invalid work record schema")
        try:
            validate_id(data["id"], "work id")
            validate_id(data["watchtower_id"], "watchtower id")
            metadata = validate_metadata(data.get("metadata", {}), normalize=False)
        except Exception as exc:
            raise UnsafeStateError(f"invalid work record: {exc}") from exc
        return Work(data["id"], data["watchtower_id"], data["state"], metadata or None)
