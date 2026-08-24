import uuid
from datetime import datetime
import unicodedata
from dataclasses import replace
from pathlib import Path

from zxro.contract import Artifact, Settlement, Turn
from zxro.errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from zxro.ids import lexical_absolute, safe_string, validate_event_id, validate_id, validate_turn_id
from .ioutil import atomic_create, atomic_replace, list_records, mutation, read_json, reading


class LocalTurnStore:
    def __init__(self, home: Path, work):
        self.home, self.work = home, work

    def create(self, work_id, agent, session, cwd, native_session_id=None, native_session_source=None):
        work_id = validate_id(work_id, "work id")
        agent, session = safe_string(agent, "agent"), safe_string(session, "session")
        native_session_id = safe_string(native_session_id, "native session id", required=False)
        native_session_source = safe_string(native_session_source, "native session source", required=False)
        if native_session_source is not None and native_session_id is None:
            raise ValidationError("native session source requires a native session id")
        cwd = lexical_absolute(cwd)
        self.work.get(work_id)
        with mutation(self.home) as access:
            owner = self.work.get_from(access, work_id)
            record = Turn(
                id=str(uuid.uuid4()),
                work_id=work_id,
                watchtower_id=owner.watchtower_id,
                runtime="acpx",
                agent=agent,
                session=session,
                cwd=cwd,
                state="running",
                native_session_id=native_session_id,
                native_session_source=native_session_source,
            )
            atomic_create(access, "turns", f"{record.id}.json", record.to_dict())
        return record

    def get(self, id):
        id = validate_turn_id(id)
        with reading(self.home) as access:
            return self.get_from(access, id)

    def bind(self, id, native_session_id=None, native_session_source=None):
        id = validate_turn_id(id)
        native_session_id = safe_string(native_session_id, "native session id", required=False)
        native_session_source = safe_string(native_session_source, "native session source", required=False)
        if native_session_id is None and native_session_source is None:
            raise ValidationError("native session id or native session source is required")
        with reading(self.home) as access:
            self.get_from(access, id)
        with mutation(self.home) as access:
            record = self.get_from(access, id)
            if native_session_id is not None and record.native_session_id not in (None, native_session_id):
                raise ConflictError("cannot change native session id")
            if native_session_source is not None and record.native_session_source not in (None, native_session_source):
                raise ConflictError("cannot change native session source")
            bound_id = record.native_session_id or native_session_id
            bound_source = record.native_session_source or native_session_source
            if bound_source is not None and bound_id is None:
                raise ValidationError("native session source requires a native session id")
            if (bound_id, bound_source) == (record.native_session_id, record.native_session_source):
                return record
            updated = replace(
                record,
                native_session_id=bound_id,
                native_session_source=bound_source,
            )
            atomic_replace(access, "turns", f"{record.id}.json", updated.to_dict())
        return updated

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
        if state is not None and state not in {"running", "settled"}:
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
        optional = {"native_session_id", "native_session_source", "outcome", "summary", "artifact_refs", "settlement"}
        string_fields = required | ({"native_session_id", "native_session_source", "outcome", "summary"} & set(data))
        if set(data) - required - optional or not required <= set(data) or any(not isinstance(data.get(key), str) for key in string_fields):
            raise UnsafeStateError("invalid turn record schema")
        try:
            validate_turn_id(data["id"])
            validate_id(data["work_id"], "work id")
            validate_id(data["watchtower_id"], "watchtower id")
            for key in ("runtime", "agent", "session"):
                safe_string(data[key], key)
            if "native_session_id" in data:
                safe_string(data["native_session_id"], "native session id")
            if "native_session_source" in data:
                safe_string(data["native_session_source"], "native session source")
            if data.get("native_session_source") is not None and data.get("native_session_id") is None:
                raise ValueError("native session source requires a native session id")
            normalized_cwd = lexical_absolute(data["cwd"])
        except Exception as exc:
            raise UnsafeStateError(f"invalid turn record: {exc}") from exc
        if data["runtime"] != "acpx" or data["state"] not in {"running", "settled"} or normalized_cwd != data["cwd"]:
            raise UnsafeStateError("invalid turn invariant")
        if data["state"] == "running" and set(data) & {"outcome", "summary", "artifact_refs", "settlement"}:
            raise UnsafeStateError("running turn has settlement fields")
        if data["state"] == "settled":
            if not {"outcome", "summary", "settlement"} <= set(data) or not isinstance(data.get("artifact_refs", []), list) or not isinstance(data["settlement"], dict):
                raise UnsafeStateError("settled turn lacks settlement fields")
            try:
                settlement = Settlement(**data["settlement"])
                safe_string(settlement.source, "source")
                if settlement.outcome not in {"completed", "failed", "cancelled"}:
                    raise ValueError("invalid outcome")
                safe_string(settlement.summary, "summary")
                if len(settlement.summary) > 1000 or unicodedata.normalize("NFC", settlement.summary) != settlement.summary:
                    raise ValueError("invalid summary normalization or length")
                validate_event_id(settlement.event_id)
                settled_at = datetime.fromisoformat(settlement.settled_at)
                if settled_at.utcoffset() is None:
                    raise ValueError("settlement timestamp lacks UTC offset")
                if settlement.payload_sha256 is not None:
                    if not isinstance(settlement.payload_sha256, str) or len(settlement.payload_sha256) != 64:
                        raise ValueError("invalid payload digest")
                    bytes.fromhex(settlement.payload_sha256)
                artifact_refs = tuple(data.get("artifact_refs", []))
                parsed_refs = [Artifact.parse_ref(ref) for ref in artifact_refs]
                if any(turn_id != data["id"] for turn_id, _ in parsed_refs) or len(set(artifact_refs)) != len(artifact_refs):
                    raise ValueError("invalid artifact references")
                if data["outcome"] != settlement.outcome or data["summary"] != settlement.summary:
                    raise ValueError("settlement fields disagree")
                if bool(artifact_refs) != (settlement.payload_sha256 is not None):
                    raise ValueError("settlement payload fields disagree")
                data["settlement"] = settlement
                data["artifact_refs"] = artifact_refs
            except Exception as exc:
                raise UnsafeStateError("invalid settlement record") from exc
        return Turn(**data)
