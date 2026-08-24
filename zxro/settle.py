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
from .localfs.ioutil import MAX_RECORD_BYTES, atomic_replace, list_names, mutation, read_json


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
            return {"watchtower_id": watchtower_id, "ack": 0}
        if set(value) != {"watchtower_id", "ack"} or value["watchtower_id"] != watchtower_id or not isinstance(value["ack"], int) or value["ack"] < 0:
            raise UnsafeStateError("invalid mailbox record schema")
        return value

    @staticmethod
    def _all_events(access):
        events = []
        for name in list_names(access, "inbox-events"):
            event = MailboxEvent.from_dict(read_json(access, "inbox-events", name))
            expected = f"{event.watchtower_id}--{event.generation:020d}--{event.event_id}.json"
            if name != expected:
                raise UnsafeStateError("mailbox event does not match its path")
            events.append(event)
        if len({event.event_id for event in events}) != len(events):
            raise UnsafeStateError("duplicate global event identity")
        return events

    @classmethod
    def _mailbox_events(cls, access, watchtower_id):
        events = sorted((event for event in cls._all_events(access) if event.watchtower_id == watchtower_id), key=lambda event: event.generation)
        if any(event.generation != index for index, event in enumerate(events, 1)):
            raise UnsafeStateError("invalid mailbox event ordering")
        return events

    @staticmethod
    def _handled(access, event_id):
        try:
            value = read_json(access, "inbox-handled", f"{event_id}.json")
        except NotFoundError:
            return None
        if set(value) != {"event_id", "watchtower_id", "handled_at"} or value["event_id"] != event_id or not all(isinstance(item, str) for item in value.values()):
            raise UnsafeStateError("invalid handled state")
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
                payload_conflicts = payload is not None and existing.payload_sha256 != digest
                if existing.outcome != outcome or existing.summary != message or payload_conflicts:
                    raise ConflictError("turn already has a different settlement")
            all_events = self._all_events(access)
            events = [event for event in all_events if event.watchtower_id == turn.watchtower_id]
            matches = [event for event in all_events if event.event_id == turn.settlement.event_id]
            if len(matches) > 1:
                raise UnsafeStateError("duplicate settlement event")
            generation = matches[0].generation if matches else len(events) + 1
            expected = MailboxEvent(turn.settlement.event_id, generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.settlement.outcome, turn.settlement.summary, turn.artifact_refs, turn.settlement.settled_at)
            if matches:
                event = matches[0]
                if event != expected:
                    raise UnsafeStateError("settlement event does not match committed turn")
            else:
                event = expected
                filename = f"{turn.watchtower_id}--{event.generation:020d}--{event.event_id}.json"
                atomic_replace(access, "inbox-events", filename, event.to_dict())
            return turn, event

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
            events = self._mailbox_events(access, watchtower_id)
            if box["ack"] > len(events):
                raise UnsafeStateError("ack exceeds mailbox history")
            return [event for event in events if self._handled(access, event.event_id) is None] if pending else [event for event in events if event.generation > box["ack"]]

    def ack(self, watchtower_id, through):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with mutation(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
            highest = len(self._mailbox_events(access, watchtower_id))
            if through < box["ack"] or through > highest:
                raise ConflictError(f"cannot acknowledge generation {through}")
            box["ack"] = through
            atomic_replace(access, "inbox", f"{watchtower_id}.json", box)
        return {"watchtower_id": watchtower_id, "through_generation": through}

    def handle(self, event_id, watchtower_id=None):
        event_id = validate_event_id(event_id)
        with mutation(self.home) as access:
            matches = [MailboxEvent.from_dict(read_json(access, "inbox-events", name)) for name in list_names(access, "inbox-events") if name.endswith(f"--{event_id}.json")]
            if watchtower_id is not None:
                validate_id(watchtower_id, "watchtower id")
                matches = [event for event in matches if event.watchtower_id == watchtower_id]
            if not matches:
                raise NotFoundError(f"event not found: {event_id}")
            if len(matches) != 1:
                raise UnsafeStateError("event identity is not unique")
            event = matches[0]
            handled = self._handled(access, event_id)
            if handled is None:
                handled = {"event_id": event_id, "watchtower_id": event.watchtower_id, "handled_at": timestamp()}
                atomic_replace(access, "inbox-handled", f"{event_id}.json", handled)
            elif handled["watchtower_id"] != event.watchtower_id:
                raise UnsafeStateError("handled state owner mismatch")
            return handled

    def artifact_path(self, ref):
        artifact = Artifact.parse_ref(ref)
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
