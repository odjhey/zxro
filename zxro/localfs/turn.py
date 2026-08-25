import uuid
from dataclasses import replace
from datetime import datetime
import unicodedata
from pathlib import Path

from zxro.contract import Artifact, ArtifactMetadata, Settlement, Turn
from zxro.errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from zxro.ids import lexical_absolute, safe_string, validate_event_id, validate_id, validate_turn_id
from .ioutil import atomic_create, atomic_replace, list_records, mutation, read_json, reading


def _binding_string(value, label):
    value = safe_string(value, label)
    if len(value) > 256:
        raise ValidationError(f"invalid {label}: maximum length is 256 characters")
    return value


class LocalTurnStore:
    def __init__(self, home: Path, work):
        self.home, self.work = home, work

    def create(self, work_id, agent, session, cwd, native_session_id=None):
        work_id = validate_id(work_id, "work id")
        agent, session = safe_string(agent, "agent"), safe_string(session, "session")
        if native_session_id is not None:
            native_session_id = _binding_string(native_session_id, "native session id")
        cwd = lexical_absolute(cwd)
        self.work.get(work_id)
        with mutation(self.home) as access:
            owner = self.work.get_from(access, work_id)
            if owner.state == "closed":
                raise ConflictError(f"cannot create a turn for closed work: {work_id}")
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
        if record.artifact_refs and (not record.artifacts or any(item.sha256 is None for item in record.artifacts)):
            metadata = []
            try:
                if not record.artifacts:
                    if record.state != "settled" or record.artifact_refs != (f"artifact:{record.id}:stdin",):
                        raise ValueError("reference-only metadata is not a master-format stdin settlement")
                    candidates = (ArtifactMetadata(record.artifact_refs[0], "stdin", 0),)
                else:
                    candidates = record.artifacts
                for item in candidates:
                    turn_id, kind = Artifact.parse_ref(item.ref)
                    artifact = Artifact.from_dict(read_json(access, "artifacts", Artifact.record_name("turn", turn_id, kind)))
                    if kind != "stdin" or record.settlement is None or artifact.sha256 != record.settlement.payload_sha256:
                        raise ValueError("legacy metadata has no trusted digest")
                    if record.artifacts and (item.bytes != artifact.bytes or item.kind != artifact.kind):
                        raise ValueError("legacy metadata does not match artifact")
                    metadata.append(ArtifactMetadata(artifact.ref, artifact.kind, artifact.bytes, artifact.sha256))
            except Exception as exc:
                raise UnsafeStateError("cannot load legacy turn artifact metadata") from exc
            record = Turn(**{**record.to_dict(), "artifact_refs": record.artifact_refs, "artifacts": tuple(metadata), "settlement": record.settlement})
        return record

    def bind(self, id, native_session_id, source):
        id = validate_turn_id(id)
        native_session_id = _binding_string(native_session_id, "native session id")
        source = _binding_string(source, "native session source")
        with mutation(self.home) as access:
            record = self.get_from(access, id)
            if record.native_session_id is not None and record.native_session_id != native_session_id:
                raise ConflictError(f"turn has a different native session id: {id}")
            if record.native_session_source is not None and record.native_session_source != source:
                raise ConflictError(f"turn has a different native session source: {id}")
            if record.native_session_id == native_session_id and record.native_session_source == source:
                return record
            bound = replace(record, native_session_id=native_session_id, native_session_source=source)
            atomic_replace(access, "turns", f"{id}.json", bound.to_dict())
            return bound

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
        optional = {"native_session_id", "native_session_source", "outcome", "summary", "verdict", "needs", "artifact_refs", "artifacts", "settlement"}
        string_fields = required | ({"native_session_id", "native_session_source", "outcome", "summary", "verdict", "needs"} & set(data))
        if set(data) - required - optional or not required <= set(data) or any(not isinstance(data.get(key), str) for key in string_fields):
            raise UnsafeStateError("invalid turn record schema")
        try:
            validate_turn_id(data["id"])
            validate_id(data["work_id"], "work id")
            validate_id(data["watchtower_id"], "watchtower id")
            for key in ("runtime", "agent", "session"):
                safe_string(data[key], key)
            if "native_session_id" in data:
                _binding_string(data["native_session_id"], "native session id")
            if "native_session_source" in data:
                _binding_string(data["native_session_source"], "native session source")
                if "native_session_id" not in data:
                    raise ValueError("native session source lacks native session id")
            normalized_cwd = lexical_absolute(data["cwd"])
        except Exception as exc:
            raise UnsafeStateError(f"invalid turn record: {exc}") from exc
        if data["runtime"] != "acpx" or data["state"] not in {"running", "settled"} or normalized_cwd != data["cwd"]:
            raise UnsafeStateError("invalid turn invariant")
        if data["state"] == "running" and set(data) & {"outcome", "summary", "verdict", "needs", "settlement"}:
            raise UnsafeStateError("running turn has settlement fields")
        try:
            artifact_refs = tuple(data.get("artifact_refs", []))
            metadata_values = data.get("artifacts", [])
            if not isinstance(data.get("artifact_refs", []), list) or not isinstance(metadata_values, list):
                raise ValueError("invalid artifact collections")
            artifacts = tuple(ArtifactMetadata(**item) for item in metadata_values)
            parsed_refs = [Artifact.parse_ref(ref) for ref in artifact_refs]
            valid_metadata = all(
                set(item) in ({"ref", "kind", "bytes"}, {"ref", "kind", "bytes", "sha256"})
                for item in metadata_values
            ) and all(
                Artifact.parse_ref(item.ref) == (data["id"], item.kind)
                and type(item.bytes) is int and item.bytes >= 0
                and (item.sha256 is None or (
                    isinstance(item.sha256, str) and len(item.sha256) == 64
                    and len(bytes.fromhex(item.sha256)) == 32
                ))
                for item in artifacts
            )
            if (any(turn_id != data["id"] for turn_id, _ in parsed_refs)
                    or len(set(artifact_refs)) != len(artifact_refs)
                    or len(artifact_refs) > 32
                    or (artifacts and len(artifact_refs) != len(artifacts))
                    or (artifacts and tuple(item.ref for item in artifacts) != artifact_refs)
                    or len(artifacts) > 32 or not valid_metadata):
                raise ValueError("invalid artifact metadata")
            data["artifact_refs"], data["artifacts"] = artifact_refs, artifacts
        except Exception as exc:
            raise UnsafeStateError("invalid artifact metadata") from exc
        if data["state"] == "settled":
            if not {"outcome", "summary", "settlement"} <= set(data) or not isinstance(data["settlement"], dict):
                raise UnsafeStateError("settled turn lacks settlement fields")
            try:
                settlement_data = data["settlement"]
                if "verdict" in settlement_data and not isinstance(settlement_data["verdict"], str):
                    raise ValueError("invalid settlement verdict")
                if "needs" in settlement_data and not isinstance(settlement_data["needs"], str):
                    raise ValueError("invalid settlement needs")
                settlement = Settlement(**settlement_data)
                safe_string(settlement.source, "source")
                if settlement.outcome not in {"completed", "failed", "cancelled"}:
                    raise ValueError("invalid outcome")
                safe_string(settlement.summary, "summary")
                if len(settlement.summary) > 1000 or unicodedata.normalize("NFC", settlement.summary) != settlement.summary:
                    raise ValueError("invalid summary normalization or length")
                if settlement.verdict not in {None, "done", "partial", "blocked"}:
                    raise ValueError("invalid verdict")
                if (settlement.verdict == "blocked") != (settlement.needs is not None):
                    raise ValueError("needs must accompany blocked verdict")
                if settlement.needs is not None:
                    safe_string(settlement.needs, "needs")
                    if len(settlement.needs) > 1000 or unicodedata.normalize("NFC", settlement.needs) != settlement.needs:
                        raise ValueError("invalid needs normalization or length")
                validate_event_id(settlement.event_id)
                settled_at = datetime.fromisoformat(settlement.settled_at)
                if settled_at.utcoffset() is None:
                    raise ValueError("settlement timestamp lacks UTC offset")
                if settlement.payload_sha256 is not None:
                    if not isinstance(settlement.payload_sha256, str) or len(settlement.payload_sha256) != 64:
                        raise ValueError("invalid payload digest")
                    bytes.fromhex(settlement.payload_sha256)
                if data["outcome"] != settlement.outcome or data["summary"] != settlement.summary:
                    raise ValueError("settlement fields disagree")
                if data.get("verdict") != settlement.verdict or data.get("needs") != settlement.needs:
                    raise ValueError("settlement verdict fields disagree")
                stdin = next((item for item in data["artifacts"] if item.kind == "stdin"), None)
                if data["artifacts"]:
                    payload_present = stdin is not None
                else:
                    payload_present = bool(data["artifact_refs"])
                    if payload_present and data["artifact_refs"] != (f"artifact:{data['id']}:stdin",):
                        raise ValueError("invalid reference-only settlement metadata")
                if payload_present != (settlement.payload_sha256 is not None):
                    raise ValueError("settlement payload fields disagree")
                data["settlement"] = settlement
            except Exception as exc:
                raise UnsafeStateError("invalid settlement record") from exc
        return Turn(**data)
