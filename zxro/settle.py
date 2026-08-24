import hashlib
import json
import os
import unicodedata
import uuid
from datetime import datetime

from .contract import Artifact, MailboxEvent, Settlement, Turn
from .errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from .ids import safe_string, validate_event_id, validate_id, validate_turn_id
from .localfs.home import check_stat
from .localfs.ioutil import MAX_RECORD_BYTES, atomic_replace, mutation, read_json, reading


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
            return {"watchtower_id": watchtower_id, "ack": 0, "highest": 0, "unresolved": []}
        required = {"watchtower_id", "ack", "highest", "unresolved"}
        valid_numbers = type(value.get("ack")) is int and type(value.get("highest")) is int
        if set(value) != required or value.get("watchtower_id") != watchtower_id or not valid_numbers or value["ack"] < 0 or value["highest"] < value["ack"] or not isinstance(value["unresolved"], list):
            raise UnsafeStateError("invalid mailbox record schema")
        try:
            unresolved = [validate_event_id(item) for item in value["unresolved"]]
        except ValidationError as exc:
            raise UnsafeStateError("invalid mailbox unresolved index") from exc
        if len(set(unresolved)) != len(unresolved):
            raise UnsafeStateError("duplicate unresolved event")
        return value

    @staticmethod
    def _event(access, watchtower_id, generation):
        event = MailboxEvent.from_dict(read_json(access, "inbox-events", f"{watchtower_id}--{generation:020d}.json"))
        if event.watchtower_id != watchtower_id or event.generation != generation:
            raise UnsafeStateError("mailbox event does not match its path")
        return event

    @staticmethod
    def _event_by_id(access, event_id):
        value = read_json(access, "inbox-index", f"{event_id}.json")
        if set(value) != {"event_id", "watchtower_id", "generation"} or value.get("event_id") != event_id or type(value.get("generation")) is not int:
            raise UnsafeStateError("invalid event index")
        try:
            watchtower_id = validate_id(value["watchtower_id"], "watchtower id")
        except ValidationError as exc:
            raise UnsafeStateError("invalid event index") from exc
        event = LocalDurableLoop._event(access, watchtower_id, value["generation"])
        if event.event_id != event_id:
            raise UnsafeStateError("event index does not match event")
        return event

    def _validate_event(self, access, event):
        try:
            turn = self.turns.get_from(access, event.turn_id)
        except NotFoundError as exc:
            raise UnsafeStateError("mailbox event references missing turn") from exc
        expected = MailboxEvent(turn.settlement.event_id, event.generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at) if turn.state == "settled" else None
        if expected != event:
            raise UnsafeStateError("mailbox event does not match terminal turn")
        for ref in event.artifact_refs:
            turn_id, kind = Artifact.parse_ref(ref)
            try:
                artifact = Artifact.from_dict(read_json(access, "artifacts", f"{turn_id}--{kind}.json"))
            except NotFoundError as exc:
                raise UnsafeStateError("mailbox event references missing artifact") from exc
            if artifact.ref != ref or artifact.turn_id != event.turn_id:
                raise UnsafeStateError("mailbox event artifact does not match durable metadata")
        return event

    def settle(self, turn_id, source, outcome, message, payload):
        turn_id = validate_turn_id(turn_id)
        source = safe_string(source, "source")
        if outcome not in {"completed", "failed", "cancelled"}:
            raise ValidationError(f"invalid settlement status: {outcome!r}")
        message = summary(message)
        digest = hashlib.sha256(payload).hexdigest() if payload is not None else None
        with reading(self.home) as access:
            self.turns.get_from(access, turn_id)
        with mutation(self.home) as access:
            turn = self.turns.get_from(access, turn_id)
            box = self._mailbox(access, turn.watchtower_id)
            if box["highest"]:
                try:
                    self._event(access, turn.watchtower_id, box["highest"])
                    if box["highest"] > 1:
                        self._event(access, turn.watchtower_id, box["highest"] - 1)
                except NotFoundError as exc:
                    raise UnsafeStateError("mailbox high-water references missing event") from exc
            if turn.state == "running":
                event_id = "evt-" + uuid.uuid4().hex
                artifact_refs = ()
                if payload is not None:
                    ref = f"artifact:{turn_id}:stdin"
                    artifact = Artifact(ref, turn_id, "stdin", len(payload), digest, payload.hex()).to_dict()
                    encoded_size = len((json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
                    if encoded_size > MAX_RECORD_BYTES:
                        raise ValidationError(f"stdin payload too large to store as a durable artifact: {len(payload)} bytes")
                    atomic_replace(access, "artifacts", f"{turn_id}--stdin.json", artifact)
                    artifact_refs = (ref,)
                settled_at = timestamp()
                settlement = Settlement(source, outcome, message, digest, event_id, settled_at)
                turn = Turn(**{**turn.to_dict(), "state": "settled", "outcome": outcome, "summary": message, "artifact_refs": artifact_refs, "settlement": settlement})
                atomic_replace(access, "turns", f"{turn.id}.json", turn.to_dict())
                if os.environ.get("ZXRO_FAULT_EXIT_AFTER") == "turn-commit":
                    os._exit(86)
            else:
                existing = turn.settlement
                if existing.outcome != outcome or existing.summary != message or (payload is not None and existing.payload_sha256 != digest):
                    raise ConflictError("turn already has a different settlement")
            try:
                event = self._event_by_id(access, turn.settlement.event_id)
            except NotFoundError:
                generation = box["highest"] + 1
                event = MailboxEvent(turn.settlement.event_id, generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at)
                atomic_replace(access, "inbox-events", f"{turn.watchtower_id}--{generation:020d}.json", event.to_dict())
                atomic_replace(access, "inbox-index", f"{event.event_id}.json", {"event_id": event.event_id, "watchtower_id": event.watchtower_id, "generation": generation})
                box["highest"] = generation
                box["unresolved"].append(event.event_id)
                atomic_replace(access, "inbox", f"{turn.watchtower_id}.json", box)
            self._validate_event(access, event)
            return turn, event

    def unread(self, watchtower_id):
        return self._events(watchtower_id, pending=False)

    def pending(self, watchtower_id):
        return self._events(watchtower_id, pending=True)

    def _events(self, watchtower_id, pending):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with reading(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
            try:
                if pending:
                    events = [self._event_by_id(access, event_id) for event_id in box["unresolved"]]
                else:
                    events = [self._event(access, watchtower_id, generation) for generation in range(box["ack"] + 1, box["highest"] + 1)]
            except NotFoundError as exc:
                raise UnsafeStateError("mailbox index references missing event") from exc
            return [self._validate_event(access, event) for event in events]

    def ack(self, watchtower_id, through):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with reading(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
        with mutation(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
            if through < box["ack"] or through > box["highest"]:
                raise ConflictError(f"cannot acknowledge generation {through}")
            box["ack"] = through
            atomic_replace(access, "inbox", f"{watchtower_id}.json", box)
        return {"watchtower_id": watchtower_id, "through_generation": through}

    def handle(self, event_id, watchtower_id=None):
        event_id = validate_event_id(event_id)
        with reading(self.home) as access:
            event = self._event_by_id(access, event_id)
            if watchtower_id is not None and event.watchtower_id != validate_id(watchtower_id, "watchtower id"):
                raise NotFoundError(f"event not found: {event_id}")
            self._validate_event(access, event)
        with mutation(self.home) as access:
            event = self._validate_event(access, self._event_by_id(access, event_id))
            box = self._mailbox(access, event.watchtower_id)
            if event_id in box["unresolved"]:
                box["unresolved"].remove(event_id)
                atomic_replace(access, "inbox", f"{event.watchtower_id}.json", box)
            handled = {"event_id": event_id, "watchtower_id": event.watchtower_id, "handled_at": timestamp()}
            try:
                existing = read_json(access, "inbox-handled", f"{event_id}.json")
            except NotFoundError:
                atomic_replace(access, "inbox-handled", f"{event_id}.json", handled)
            else:
                handled = existing
                try:
                    handled_at = datetime.fromisoformat(handled.get("handled_at", ""))
                    valid = set(handled) == {"event_id", "watchtower_id", "handled_at"}
                    valid = valid and handled["event_id"] == event_id and handled["watchtower_id"] == event.watchtower_id
                    valid = valid and handled_at.utcoffset() is not None
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    raise UnsafeStateError("invalid handled state")
            return handled

    def artifact_path(self, ref):
        artifact = Artifact.parse_ref(ref)
        with reading(self.home) as access:
            Artifact.from_dict(read_json(access, "artifacts", f"{artifact[0]}--{artifact[1]}.json"))
        with mutation(self.home) as access:
            record = Artifact.from_dict(read_json(access, "artifacts", f"{artifact[0]}--{artifact[1]}.json"))
            if Artifact.parse_ref(record.ref) != artifact:
                raise UnsafeStateError("artifact record does not match requested reference")
            filename = f"{record.turn_id}--{record.kind}.bin"
            path = self.home / "artifacts" / filename
            content = bytes.fromhex(record.content_hex)
            with access.directory("artifacts") as directory_fd:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = None
                try:
                    try:
                        fd = os.open(filename, flags, dir_fd=directory_fd)
                    except FileNotFoundError:
                        try:
                            fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
                            view = memoryview(content)
                            while view:
                                view = view[os.write(fd, view):]
                            os.fsync(fd)
                            os.fchmod(fd, 0o400)
                        except FileExistsError:
                            fd = os.open(filename, flags, dir_fd=directory_fd)
                    info = os.fstat(fd)
                    check_stat(info, path, directory=False)
                    if info.st_mode & 0o222:
                        raise UnsafeStateError("artifact materialization is writable")
                    os.lseek(fd, 0, os.SEEK_SET)
                    chunks = []
                    while True:
                        chunk = os.read(fd, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    actual = b"".join(chunks)
                    entry = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
                    check_stat(entry, path, directory=False)
                    if (entry.st_dev, entry.st_ino) != (info.st_dev, info.st_ino):
                        raise UnsafeStateError("artifact path changed during verification")
                except OSError as exc:
                    raise UnsafeStateError(f"cannot verify artifact path: {exc}") from exc
                finally:
                    if fd is not None:
                        os.close(fd)
                if len(actual) != record.bytes or hashlib.sha256(actual).hexdigest() != record.sha256:
                    raise UnsafeStateError("artifact path does not match durable content")
            return {"ref": ref, "path": str(path), "bytes": record.bytes}
