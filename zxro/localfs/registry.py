from pathlib import Path

from zxro.contract import Watchtower
from zxro.errors import UnsafeStateError
from zxro.ids import lexical_absolute, safe_string, validate_id
from .home import check_owned_mode
from .ioutil import atomic_create, list_records, mutation, read_json


class LocalRegistry:
    def __init__(self, home: Path):
        self.home = home

    def create(self, id, cwd, agent=None, session=None):
        id = validate_id(id, "watchtower id")
        record = Watchtower(id, lexical_absolute(cwd), safe_string(agent, "agent", required=False), safe_string(session, "session", required=False))
        with mutation(self.home):
            atomic_create(self.home / "watchtowers" / f"{id}.json", record.to_dict())
        return record

    def get(self, id):
        id = validate_id(id, "watchtower id")
        return self._decode(read_json(self.home / "watchtowers" / f"{id}.json"))

    def list(self):
        directory = self.home / "watchtowers"
        if self.home.exists() or self.home.is_symlink():
            check_owned_mode(self.home, directory=True)
        if not directory.exists() and not directory.is_symlink():
            return []
        return sorted((self._decode(item) for item in list_records(directory)), key=lambda item: item.id)

    @staticmethod
    def _decode(data):
        required = {"id": str, "cwd": str}
        optional = {"agent": str, "session": str}
        if set(data) - set(required) - set(optional) or any(not isinstance(data.get(key), kind) for key, kind in required.items()) or any(key in data and not isinstance(data[key], kind) for key, kind in optional.items()):
            raise UnsafeStateError("invalid watchtower record schema")
        try:
            validate_id(data["id"], "watchtower id")
            lexical_absolute(data["cwd"])
            for key in optional:
                if key in data:
                    safe_string(data[key], key)
        except Exception as exc:
            raise UnsafeStateError(f"invalid watchtower record: {exc}") from exc
        if lexical_absolute(data["cwd"]) != data["cwd"]:
            raise UnsafeStateError("watchtower cwd is not lexical absolute")
        return Watchtower(**data)
