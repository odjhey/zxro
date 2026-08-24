import uuid
from pathlib import Path

from zxro.contract import Turn
from zxro.errors import NotFoundError, UnsafeStateError, ValidationError
from zxro.ids import lexical_absolute, safe_string, validate_id, validate_turn_id
from .ioutil import atomic_create, list_records, mutation, read_json, reading


class LocalTurnStore:
    def __init__(self, home: Path, work):
        self.home, self.work = home, work

    def create(self, work_id, agent, session, cwd, native_session_id=None):
        work_id = validate_id(work_id, "work id")
        agent, session = safe_string(agent, "agent"), safe_string(session, "session")
        native_session_id = safe_string(native_session_id, "native session id", required=False)
        cwd = lexical_absolute(cwd)
        self.work.get(work_id)
        with mutation(self.home) as access:
            owner = self.work.get_from(access, work_id)
            record = Turn(str(uuid.uuid4()), work_id, owner.watchtower_id, "acpx", agent, session, cwd, "running", native_session_id)
            atomic_create(access, "turns", f"{record.id}.json", record.to_dict())
        return record

    def get(self, id):
        id = validate_turn_id(id)
        with reading(self.home) as access:
            return self.get_from(access, id)

    def get_from(self, access, id):
        record = self._decode(read_json(access, "turns", f"{id}.json"))
        try:
            owner = self.work.get_from(access, record.work_id)
        except Exception as exc:
            raise UnsafeStateError(f"invalid turn ownership: {exc}") from exc
        if owner.watchtower_id != record.watchtower_id:
            raise UnsafeStateError("turn watchtower does not match work owner")
        return record

    def list(self, work_id=None, state=None):
        if work_id is not None:
            validate_id(work_id, "work id")
        if state is not None and state != "running":
            raise ValidationError(f"invalid turn state: {state!r}")
        try:
            with reading(self.home) as access:
                records = [self._decode(item) for item in list_records(access, "turns")]
                for record in records:
                    try:
                        owner = self.work.get_from(access, record.work_id)
                    except Exception as exc:
                        raise UnsafeStateError(f"invalid turn ownership: {exc}") from exc
                    if owner.watchtower_id != record.watchtower_id:
                        raise UnsafeStateError("turn watchtower does not match work owner")
        except NotFoundError:
            return []
        return sorted((item for item in records if (work_id is None or item.work_id == work_id) and (state is None or item.state == state)), key=lambda item: item.id)

    @staticmethod
    def _decode(data):
        required = {"id", "work_id", "watchtower_id", "runtime", "agent", "session", "cwd", "state"}
        optional = {"native_session_id"}
        if set(data) - required - optional or not required <= set(data) or any(not isinstance(data.get(key), str) for key in required | (optional & set(data))):
            raise UnsafeStateError("invalid turn record schema")
        try:
            validate_turn_id(data["id"])
            validate_id(data["work_id"], "work id")
            validate_id(data["watchtower_id"], "watchtower id")
            for key in ("runtime", "agent", "session"):
                safe_string(data[key], key)
            if "native_session_id" in data:
                safe_string(data["native_session_id"], "native session id")
            normalized_cwd = lexical_absolute(data["cwd"])
        except Exception as exc:
            raise UnsafeStateError(f"invalid turn record: {exc}") from exc
        if data["runtime"] != "acpx" or data["state"] != "running" or normalized_cwd != data["cwd"]:
            raise UnsafeStateError("invalid turn invariant")
        return Turn(**data)
