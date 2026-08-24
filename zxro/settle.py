import hashlib
import os
import unicodedata
import uuid
from datetime import datetime

from .contract import Artifact, MailboxEvent, Settlement, Turn
from .errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from .ids import safe_string, validate_event_id, validate_id, validate_turn_id
from .localfs.ioutil import atomic_replace, mutation, read_json


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def summary(value):
    value = unicodedata.normalize("NFC", safe_string(value, "message"))
    if len(value) > 1000:
        raise ValidationError("message exceeds 1000 Unicode characters")
    return value


class LocalDurableLoop:
    def __init__(self, home, turns, registry=None):
        self.home, self.turns, self.registry = home, turns, registry

    @staticmethod
    def _mailbox(access, watchtower_id):
        try:
            value = read_json(access, "inbox", f"{watchtower_id}.json")
        except NotFoundError:
            return {"watchtower_id": watchtower_id, "ack": 0, "events": [], "handled": {}}
        if set(value) != {"watchtower_id", "ack", "events", "handled"} or value["watchtower_id"] != watchtower_id or not isinstance(value["ack"], int) or value["ack"] < 0 or not isinstance(value["events"], list) or not isinstance(value["handled"], dict):
            raise UnsafeStateError("invalid mailbox record schema")
        previous = 0
        ids = set()
        for raw in value["events"]:
            event = MailboxEvent.from_dict(raw)
            if event.watchtower_id != watchtower_id or event.generation != previous + 1 or event.event_id in ids:
                raise UnsafeStateError("invalid mailbox event ordering")
            previous, _ = event.generation, ids.add(event.event_id)
        if value["ack"] > previous or set(value["handled"]) - ids or any(not isinstance(v, str) for v in value["handled"].values()):
            raise UnsafeStateError("invalid mailbox state")
        return value

    def settle(self, turn_id, source, outcome, message, payload):
        turn_id = validate_turn_id(turn_id)
        source = safe_string(source, "source")
        if outcome not in {"completed", "failed", "cancelled"}:
            raise ValidationError(f"invalid settlement status: {outcome!r}")
        message = summary(message)
        digest = hashlib.sha256(payload).hexdigest() if payload is not None else None
        with mutation(self.home) as access:
            turn = self.turns.get_from(access, turn_id)
            if turn.state == "running":
                event_id = "evt-" + uuid.uuid4().hex
                artifact_refs = ()
                if payload is not None:
                    ref = f"artifact:{turn_id}:stdin"
                    atomic_replace(access, "artifacts", f"{turn_id}--stdin.json", Artifact(ref, turn_id, "stdin", len(payload), digest, payload.hex()).to_dict())
                    artifact_refs = (ref,)
                settled_at = timestamp()
                settlement = Settlement(source, outcome, message, digest, event_id, settled_at)
                turn = Turn(**{**turn.to_dict(), "state": "settled", "outcome": outcome, "summary": message, "artifact_refs": artifact_refs, "settlement": settlement})
                atomic_replace(access, "turns", f"{turn.id}.json", turn.to_dict())
                if os.environ.get("ZXRO_FAULT_EXIT_AFTER") == "turn-commit":
                    os._exit(86)
            else:
                existing = turn.settlement
                payload_conflicts = payload is not None and existing.payload_sha256 != digest
                if existing.outcome != outcome or existing.summary != message or payload_conflicts:
                    raise ConflictError("turn already has a different settlement")
            mailbox = self._mailbox(access, turn.watchtower_id)
            matches = [event for event in mailbox["events"] if event["event_id"] == turn.settlement.event_id]
            if not matches:
                event = MailboxEvent(turn.settlement.event_id, len(mailbox["events"]) + 1, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.settlement.outcome, turn.settlement.summary, turn.artifact_refs, turn.settlement.settled_at)
                mailbox["events"].append(event.to_dict())
                atomic_replace(access, "inbox", f"{turn.watchtower_id}.json", mailbox)
            elif len(matches) != 1:
                raise UnsafeStateError("duplicate settlement event")
            return turn, MailboxEvent.from_dict(matches[0] if matches else mailbox["events"][-1])

    def unread(self, watchtower_id):
        return self._events(watchtower_id, pending=False)

    def pending(self, watchtower_id):
        return self._events(watchtower_id, pending=True)

    def _events(self, watchtower_id, pending):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with mutation(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
        raws = [e for e in box["events"] if e["event_id"] not in box["handled"]] if pending else [e for e in box["events"] if e["generation"] > box["ack"]]
        return [MailboxEvent.from_dict(e) for e in raws]

    def ack(self, watchtower_id, through):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with mutation(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
            highest = len(box["events"])
            if through < box["ack"] or through > highest:
                raise ConflictError(f"cannot acknowledge generation {through}")
            box["ack"] = through
            atomic_replace(access, "inbox", f"{watchtower_id}.json", box)
        return {"watchtower_id": watchtower_id, "through_generation": through}

    def handle(self, event_id, watchtower_id=None):
        event_id = validate_event_id(event_id)
        with mutation(self.home) as access:
            candidates = [watchtower_id] if watchtower_id else [name[:-5] for name in os.listdir(self.home / "inbox") if name.endswith(".json")]
            found = []
            for owner in candidates:
                validate_id(owner, "watchtower id")
                box = self._mailbox(access, owner)
                if any(e["event_id"] == event_id for e in box["events"]):
                    found.append((owner, box))
            if not found:
                raise NotFoundError(f"event not found: {event_id}")
            if len(found) != 1:
                raise UnsafeStateError("event identity is not unique")
            owner, box = found[0]
            box["handled"].setdefault(event_id, timestamp())
            atomic_replace(access, "inbox", f"{owner}.json", box)
            return {"event_id": event_id, "watchtower_id": owner, "handled_at": box["handled"][event_id]}

    def artifact_path(self, ref):
        artifact = Artifact.parse_ref(ref)
        with mutation(self.home) as access:
            record = Artifact.from_dict(read_json(access, "artifacts", f"{artifact[0]}--{artifact[1]}.json"))
        path = self.home / "artifacts" / f"{record.turn_id}--{record.kind}.bin"
        if not path.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(path, flags, 0o600)
                try:
                    os.write(fd, bytes.fromhex(record.content_hex)); os.fsync(fd)
                finally: os.close(fd)
            except FileExistsError: pass
        if path.is_symlink() or path.resolve().parent != (self.home / "artifacts").resolve():
            raise UnsafeStateError("unsafe artifact path")
        return {"ref": ref, "path": str(path), "bytes": record.bytes}
