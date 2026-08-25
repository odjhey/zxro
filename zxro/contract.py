from dataclasses import asdict, dataclass
from datetime import datetime
import unicodedata
from typing import Protocol


@dataclass(frozen=True)
class Watchtower:
    id: str
    cwd: str
    agent: str | None = None
    session: str | None = None

    def to_dict(self):
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class Work:
    id: str
    watchtower_id: str
    state: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Settlement:
    source: str
    outcome: str
    summary: str
    payload_sha256: str | None
    event_id: str
    settled_at: str
    verdict: str | None = None
    needs: str | None = None

    def to_dict(self):
        value = asdict(self)
        return {key: item for key, item in value.items() if key not in {"verdict", "needs"} or item is not None}


@dataclass(frozen=True)
class Artifact:
    ref: str
    turn_id: str
    kind: str
    bytes: int
    sha256: str
    content_hex: str

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def parse_ref(ref):
        parts = ref.split(":") if isinstance(ref, str) else []
        if len(parts) != 3 or parts[0] != "artifact":
            from .errors import ValidationError
            raise ValidationError(f"invalid artifact reference: {ref!r}")
        from .ids import validate_id, validate_turn_id
        return validate_turn_id(parts[1]), validate_id(parts[2], "artifact kind")

    @classmethod
    def from_dict(cls, value):
        if set(value) != {"ref", "turn_id", "kind", "bytes", "sha256", "content_hex"}:
            from .errors import UnsafeStateError
            raise UnsafeStateError("invalid artifact record schema")
        from .errors import ValidationError
        try:
            record = cls(**value)
            content = bytes.fromhex(record.content_hex)
            valid = cls.parse_ref(record.ref) == (record.turn_id, record.kind)
            valid = valid and type(record.bytes) is int and record.bytes >= 0 and record.bytes == len(content)
            valid = valid and __import__("hashlib").sha256(content).hexdigest() == record.sha256
        except (TypeError, ValueError, ValidationError) as exc:
            from .errors import UnsafeStateError
            raise UnsafeStateError("invalid artifact record") from exc
        if not valid:
            from .errors import UnsafeStateError
            raise UnsafeStateError("invalid artifact record")
        return record


@dataclass(frozen=True)
class MailboxEvent:
    event_id: str
    generation: int
    type: str
    watchtower_id: str
    work_id: str
    turn_id: str
    agent: str
    outcome: str
    summary: str
    artifact_refs: tuple[str, ...]
    created_at: str
    verdict: str | None = None
    needs: str | None = None

    def to_dict(self):
        value = asdict(self)
        value["artifact_refs"] = list(self.artifact_refs)
        return {key: item for key, item in value.items() if item is not None}

    @classmethod
    def from_dict(cls, value):
        optional = {"verdict", "needs"}
        required = set(cls.__dataclass_fields__) - optional
        if set(value) - optional != required or not isinstance(value.get("artifact_refs"), list):
            from .errors import UnsafeStateError
            raise UnsafeStateError("invalid mailbox event schema")
        from .errors import ValidationError
        from .ids import safe_string, validate_event_id, validate_id, validate_turn_id
        try:
            validate_event_id(value["event_id"])
            validate_id(value["watchtower_id"])
            validate_id(value["work_id"])
            turn_id = validate_turn_id(value["turn_id"])
            safe_string(value["agent"], "agent")
            safe_string(value["summary"], "summary")
            if len(value["summary"]) > 1000 or unicodedata.normalize("NFC", value["summary"]) != value["summary"]:
                raise ValueError("invalid summary normalization or length")
            verdict, needs = value.get("verdict"), value.get("needs")
            if verdict not in {None, "done", "partial", "blocked"}:
                raise ValueError("invalid verdict")
            if (verdict == "blocked") != (needs is not None):
                raise ValueError("needs must accompany blocked verdict")
            if needs is not None:
                safe_string(needs, "needs")
                if len(needs) > 1000 or unicodedata.normalize("NFC", needs) != needs:
                    raise ValueError("invalid needs normalization or length")
            created_at = datetime.fromisoformat(value["created_at"])
            if created_at.utcoffset() is None:
                raise ValueError
            if type(value["generation"]) is not int or value["generation"] < 1 or value["type"] != "turn_settled" or value["outcome"] not in {"completed", "failed", "cancelled"}:
                raise ValueError
            references = [Artifact.parse_ref(ref) for ref in value["artifact_refs"]]
            if any(reference[0] != turn_id for reference in references) or len(set(references)) != len(references):
                raise ValueError
        except (TypeError, ValueError, ValidationError) as exc:
            from .errors import UnsafeStateError
            raise UnsafeStateError("invalid mailbox event") from exc
        return cls(**{**value, "artifact_refs": tuple(value["artifact_refs"])})


@dataclass(frozen=True)
class Turn:
    id: str
    work_id: str
    watchtower_id: str
    runtime: str
    agent: str
    session: str
    cwd: str
    state: str
    native_session_id: str | None = None
    outcome: str | None = None
    summary: str | None = None
    verdict: str | None = None
    needs: str | None = None
    artifact_refs: tuple[str, ...] = ()
    settlement: Settlement | None = None

    def to_dict(self):
        value = asdict(self)
        value["artifact_refs"] = list(self.artifact_refs)
        if self.settlement is not None:
            value["settlement"] = self.settlement.to_dict()
        return {key: item for key, item in value.items() if item is not None and not (key == "artifact_refs" and not item)}


class Registry(Protocol):
    def create(self, id: str, cwd: str, agent: str | None = None, session: str | None = None) -> Watchtower: ...
    def get(self, id: str) -> Watchtower: ...
    def list(self) -> list[Watchtower]: ...


class WorkStore(Protocol):
    def create(self, id: str, watchtower_id: str) -> Work: ...
    def get(self, id: str) -> Work: ...
    def list(self, watchtower_id: str | None = None, state: str | None = None) -> list[Work]: ...
    def close(self, id: str) -> Work: ...


class TurnStore(Protocol):
    def create(self, work_id: str, agent: str, session: str, cwd: str, native_session_id: str | None = None) -> Turn: ...
    def get(self, id: str) -> Turn: ...
    def list(self, work_id: str | None = None, state: str | None = None) -> list[Turn]: ...


class SettlementCapability(Protocol):
    def settle(self, turn_id: str, source: str, outcome: str, message: str, payload: bytes | None, verdict: str | None = None, needs: str | None = None) -> tuple[Turn, MailboxEvent]: ...


class MailboxCapability(Protocol):
    def unread(self, watchtower_id: str) -> list[MailboxEvent]: ...
    def pending(self, watchtower_id: str) -> list[MailboxEvent]: ...
    def ack(self, watchtower_id: str, through: int) -> dict: ...
    def handle(self, event_id: str, watchtower_id: str | None = None) -> dict: ...


class ArtifactCapability(Protocol):
    def artifact_path(self, ref: str) -> dict: ...


class M1Capabilities(SettlementCapability, MailboxCapability, ArtifactCapability, Protocol):
    """Injected provider-neutral capabilities used by M1 CLI handlers."""
