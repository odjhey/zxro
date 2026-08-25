import hashlib
import json
import os
import uuid
from datetime import datetime

from ..contract import Artifact, ArtifactMetadata, MailboxEvent, Settlement, Turn
from ..errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from ..ids import safe_string, validate_event_id, validate_id, validate_turn_id
from .home import check_stat
from ..settle import MAX_STDIN_BYTES, normalize_summary, normalize_verdict
from .ioutil import MAX_RECORD_BYTES, atomic_create, atomic_replace, mutation, read_json, reading


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")



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
    def _index(access, event_id):
        value = read_json(access, "inbox-index", f"{event_id}.json")
        if set(value) != {"event_id", "watchtower_id", "generation"} or value.get("event_id") != event_id or type(value.get("generation")) is not int:
            raise UnsafeStateError("invalid event index")
        try:
            validate_id(value["watchtower_id"], "watchtower id")
        except ValidationError as exc:
            raise UnsafeStateError("invalid event index") from exc
        return value

    @staticmethod
    def _event_by_id(access, event_id):
        value = LocalDurableLoop._index(access, event_id)
        try:
            watchtower_id = value["watchtower_id"]
            event = LocalDurableLoop._event(access, watchtower_id, value["generation"])
        except ValidationError as exc:
            raise UnsafeStateError("invalid event index") from exc
        except NotFoundError as exc:
            raise UnsafeStateError("event index references missing event") from exc
        if event.event_id != event_id:
            raise UnsafeStateError("event index does not match event")
        return event

    @staticmethod
    def _validate_index(access, event):
        try:
            value = LocalDurableLoop._index(access, event.event_id)
        except NotFoundError as exc:
            raise UnsafeStateError("published event is missing its direct index") from exc
        expected = {"event_id": event.event_id, "watchtower_id": event.watchtower_id, "generation": event.generation}
        if value != expected:
            raise UnsafeStateError("published event direct index mismatch")

    @staticmethod
    def _artifact_record(access, turn_id, kind):
        return Artifact.from_dict(read_json(access, "artifacts", Artifact.record_name("turn", turn_id, kind)))

    def _validate_event(self, access, event):
        try:
            turn = self.turns.get_from(access, event.turn_id)
        except NotFoundError as exc:
            raise UnsafeStateError("mailbox event references missing turn") from exc
        expected = MailboxEvent(turn.settlement.event_id, event.generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at, turn.verdict, turn.needs) if turn.state == "settled" else None
        if expected != event:
            raise UnsafeStateError("mailbox event does not match terminal turn")
        metadata = {item.ref: item for item in turn.artifacts}
        for ref in event.artifact_refs:
            turn_id, kind = Artifact.parse_ref(ref)
            try:
                artifact = self._artifact_record(access, turn_id, kind)
            except NotFoundError as exc:
                raise UnsafeStateError("mailbox event references missing artifact") from exc
            expected_metadata = ArtifactMetadata(artifact.ref, artifact.kind, artifact.bytes, artifact.sha256)
            digest_mismatch = kind == "stdin" and artifact.sha256 != turn.settlement.payload_sha256
            if artifact.ref != ref or artifact.turn_id != event.turn_id or metadata.get(ref) != expected_metadata or digest_mismatch:
                raise UnsafeStateError("mailbox event artifact does not match durable turn metadata")
        return event

    @staticmethod
    def _fault(point):
        if os.environ.get("ZXRO_FAULT_EXIT_AFTER") == point:
            os._exit(86)

    @staticmethod
    def _handled(access, event):
        try:
            handled = read_json(access, "inbox-handled", f"{event.event_id}.json")
        except NotFoundError:
            return None
        try:
            handled_at = datetime.fromisoformat(handled.get("handled_at", ""))
            valid = set(handled) == {"event_id", "watchtower_id", "handled_at"}
            valid = valid and handled["event_id"] == event.event_id and handled["watchtower_id"] == event.watchtower_id
            valid = valid and handled_at.utcoffset() is not None
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise UnsafeStateError("invalid handled state")
        return handled

    def _reconcile_next(self, access, box):
        generation = box["highest"] + 1
        try:
            event = self._event(access, box["watchtower_id"], generation)
        except NotFoundError:
            return None
        self._validate_event(access, event)
        index = {"event_id": event.event_id, "watchtower_id": event.watchtower_id, "generation": generation}
        try:
            existing = self._index(access, event.event_id)
        except NotFoundError:
            atomic_create(access, "inbox-index", f"{event.event_id}.json", index)
        else:
            if existing != index:
                raise UnsafeStateError("event index conflicts with immutable event")
        if self._handled(access, event) is None and event.event_id not in box["unresolved"]:
            box["unresolved"].append(event.event_id)
        box["highest"] = generation
        atomic_replace(access, "inbox", f"{event.watchtower_id}.json", box)
        return event

    def _put_artifact(self, access, turn, kind, payload, *, settlement=False):
        kind = validate_id(kind, "artifact kind")
        if kind == "stdin" and not settlement:
            raise ValidationError("artifact kind 'stdin' is reserved for turn settle --stdin")
        if turn.state != "running":
            raise ConflictError(f"cannot attach artifact to settled turn: {turn.id}")
        if kind in {item.kind for item in turn.artifacts}:
            raise ConflictError(f"artifact kind already exists for turn: {kind}")
        if len(turn.artifacts) >= 32:
            raise ValidationError("turn artifact limit exceeded: maximum is 32")
        if len(payload) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        digest = hashlib.sha256(payload).hexdigest()
        ref = f"artifact:{turn.id}:{kind}"
        artifact = Artifact(ref, turn.id, kind, len(payload), digest, payload.hex())
        encoded_size = len((json.dumps(artifact.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        if encoded_size > MAX_RECORD_BYTES:
            raise ValidationError(f"stdin payload too large to store as a durable artifact: {len(payload)} bytes")
        try:
            atomic_create(access, "artifacts", Artifact.record_name("turn", turn.id, kind), artifact.to_dict())
        except ConflictError:
            existing = self._artifact_record(access, turn.id, kind)
            if existing != artifact:
                raise ConflictError(f"artifact kind already exists for turn: {kind}")
        self._fault("artifact-commit")
        metadata = ArtifactMetadata(ref, kind, len(payload), digest)
        updated = Turn(**{
            **turn.to_dict(),
            "artifact_refs": (*turn.artifact_refs, ref),
            "artifacts": (*turn.artifacts, metadata),
        })
        atomic_replace(access, "turns", f"{turn.id}.json", updated.to_dict())
        self._fault("artifact-metadata-commit")
        return updated, artifact

    def artifact_put(self, turn_id, kind, payload):
        turn_id = validate_turn_id(turn_id)
        kind = validate_id(kind, "artifact kind")
        if kind == "stdin":
            raise ValidationError("artifact kind 'stdin' is reserved for turn settle --stdin")
        if len(payload) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        # Preserve missing-home no-side-effect behavior without racing an unlocked
        # preflight read against ordinary concurrent turn updates.
        if not self.home.exists():
            with reading(self.home) as access:
                self.turns.get_from(access, turn_id)
        with mutation(self.home) as access:
            turn = self.turns.get_from(access, turn_id)
            _, artifact = self._put_artifact(access, turn, kind, payload)
            return ArtifactMetadata(artifact.ref, artifact.kind, artifact.bytes, artifact.sha256)

    def settle(self, turn_id, source, outcome, message, payload, verdict=None, needs=None):
        turn_id = validate_turn_id(turn_id)
        source = safe_string(source, "source")
        if outcome not in {"completed", "failed", "cancelled"}:
            raise ValidationError(f"invalid settlement status: {outcome!r}")
        message = normalize_summary(message)
        verdict, needs = normalize_verdict(verdict, needs)
        if payload is not None and len(payload) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        digest = hashlib.sha256(payload).hexdigest() if payload is not None else None
        with reading(self.home) as access:
            self.turns.get_from(access, turn_id)
        with mutation(self.home) as access:
            turn = self.turns.get_from(access, turn_id)
            if turn.state == "settled":
                existing = turn.settlement
                if existing.outcome != outcome or existing.summary != message or existing.verdict != verdict or existing.needs != needs or (payload is not None and existing.payload_sha256 != digest):
                    raise ConflictError("turn already has a different settlement")
            box = self._mailbox(access, turn.watchtower_id)
            if box["highest"]:
                try:
                    boundary = self._event(access, turn.watchtower_id, box["highest"])
                    self._validate_index(access, boundary)
                    if box["highest"] > 1:
                        previous = self._event(access, turn.watchtower_id, box["highest"] - 1)
                        self._validate_index(access, previous)
                except NotFoundError as exc:
                    raise UnsafeStateError("mailbox high-water references missing event") from exc
            while self._reconcile_next(access, box) is not None:
                box = self._mailbox(access, turn.watchtower_id)
            if turn.state == "running":
                event_id = "evt-" + uuid.uuid4().hex
                existing_stdin = next((item for item in turn.artifacts if item.kind == "stdin"), None)
                if existing_stdin is not None:
                    artifact = self._artifact_record(access, turn.id, "stdin")
                    expected = ArtifactMetadata(artifact.ref, artifact.kind, artifact.bytes, artifact.sha256)
                    if expected != existing_stdin:
                        raise UnsafeStateError("settlement stdin artifact does not match turn metadata")
                    if payload is not None and artifact.sha256 != digest:
                        raise ConflictError("turn already has different settlement stdin")
                    digest = artifact.sha256
                elif payload is not None:
                    turn, artifact = self._put_artifact(access, turn, "stdin", payload, settlement=True)
                    digest = artifact.sha256
                else:
                    try:
                        artifact = self._artifact_record(access, turn.id, "stdin")
                    except NotFoundError:
                        artifact = None
                    if artifact is not None:
                        metadata = ArtifactMetadata(artifact.ref, artifact.kind, artifact.bytes, artifact.sha256)
                        turn = Turn(**{
                            **turn.to_dict(),
                            "artifact_refs": (*turn.artifact_refs, artifact.ref),
                            "artifacts": (*turn.artifacts, metadata),
                        })
                        atomic_replace(access, "turns", f"{turn.id}.json", turn.to_dict())
                        self._fault("artifact-metadata-commit")
                        digest = artifact.sha256
                settled_at = timestamp()
                settlement = Settlement(source, outcome, message, digest, event_id, settled_at, verdict, needs)
                turn = Turn(**{
                    **turn.to_dict(),
                    "state": "settled",
                    "outcome": outcome,
                    "summary": message,
                    "verdict": verdict,
                    "needs": needs,
                    "artifact_refs": turn.artifact_refs,
                    "artifacts": turn.artifacts,
                    "settlement": settlement,
                })
                atomic_replace(access, "turns", f"{turn.id}.json", turn.to_dict())
                if os.environ.get("ZXRO_FAULT_EXIT_AFTER") == "turn-commit":
                    os._exit(86)
            try:
                event = self._event_by_id(access, turn.settlement.event_id)
            except NotFoundError:
                generation = box["highest"] + 1
                event = MailboxEvent(turn.settlement.event_id, generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at, turn.verdict, turn.needs)
                self._fault("before-event-commit")
                atomic_create(access, "inbox-events", f"{turn.watchtower_id}--{generation:020d}.json", event.to_dict())
                self._fault("event-commit")
                self._fault("before-index-commit")
                atomic_create(access, "inbox-index", f"{event.event_id}.json", {"event_id": event.event_id, "watchtower_id": event.watchtower_id, "generation": generation})
                self._fault("index-commit")
                self._fault("before-mailbox-commit")
                box["highest"] = generation
                box["unresolved"].append(event.event_id)
                atomic_replace(access, "inbox", f"{turn.watchtower_id}.json", box)
                self._fault("mailbox-commit")
            else:
                while event.generation > box["highest"]:
                    if self._reconcile_next(access, box) is None:
                        raise UnsafeStateError("event index is above mailbox high-water without an immutable event")
                    box = self._mailbox(access, turn.watchtower_id)
                expected = MailboxEvent(turn.settlement.event_id, event.generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at, turn.verdict, turn.needs)
                if event != expected:
                    raise UnsafeStateError("settlement event does not match committed turn")
            self._validate_event(access, event)
            return turn, event

    def unread(self, watchtower_id):
        return self._events(watchtower_id, pending=False)

    def pending(self, watchtower_id):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with reading(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
        with mutation(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
            try:
                events = [self._event_by_id(access, event_id) for event_id in box["unresolved"]]
            except NotFoundError as exc:
                raise UnsafeStateError("mailbox index references missing event") from exc
            if any(event.watchtower_id != watchtower_id for event in events):
                raise UnsafeStateError("mailbox index references another watchtower")
            visible = []
            compacted = []
            for event in events:
                self._validate_index(access, event)
                self._validate_event(access, event)
                if self._handled(access, event) is None:
                    visible.append(event)
                    compacted.append(event.event_id)
            if compacted != box["unresolved"]:
                box["unresolved"] = compacted
                atomic_replace(access, "inbox", f"{watchtower_id}.json", box)
            return visible

    def _events(self, watchtower_id, pending=False):
        watchtower_id = validate_id(watchtower_id, "watchtower id")
        with reading(self.home) as access:
            if self.registry is not None:
                self.registry.get_from(access, watchtower_id)
            box = self._mailbox(access, watchtower_id)
            try:
                events = [self._event(access, watchtower_id, generation) for generation in range(box["ack"] + 1, box["highest"] + 1)]
            except NotFoundError as exc:
                raise UnsafeStateError("mailbox index references missing event") from exc
            for event in events:
                self._validate_index(access, event)
                self._validate_event(access, event)
            return events

    def ack(self, watchtower_id, through):
        if type(through) is not int or through < 0:
            raise ValidationError(f"invalid acknowledgement generation: {through!r}")
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
            try:
                events = [self._event(access, watchtower_id, generation) for generation in range(box["ack"] + 1, through + 1)]
            except NotFoundError as exc:
                raise UnsafeStateError("ack range references missing event") from exc
            for event in events:
                self._validate_index(access, event)
                self._validate_event(access, event)
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
            handled = self._handled(access, event)
            if handled is None:
                if event.generation <= box["highest"] and event_id not in box["unresolved"]:
                    raise UnsafeStateError("published event has neither unresolved nor handled state")
                handled = {"event_id": event_id, "watchtower_id": event.watchtower_id, "handled_at": timestamp()}
                self._fault("before-handle-marker-commit")
                atomic_create(access, "inbox-handled", f"{event_id}.json", handled)
                self._fault("handle-marker-commit")
            if event_id in box["unresolved"]:
                box["unresolved"].remove(event_id)
                self._fault("before-handle-mailbox-commit")
                atomic_replace(access, "inbox", f"{event.watchtower_id}.json", box)
                self._fault("handle-mailbox-commit")
            return handled

    def _attached_artifact(self, access, ref, parsed):
        turn = self.turns.get_from(access, parsed[0])
        if ref not in turn.artifact_refs:
            raise NotFoundError(f"artifact not attached to turn: {ref}")
        record = self._artifact_record(access, parsed[0], parsed[1])
        expected = ArtifactMetadata(record.ref, record.kind, record.bytes, record.sha256)
        metadata = next((item for item in turn.artifacts if item.ref == ref), None)
        if Artifact.parse_ref(record.ref) != parsed or metadata != expected:
            raise UnsafeStateError("artifact record does not match attached turn metadata")
        return record

    def artifact_path(self, ref):
        artifact = Artifact.parse_ref(ref)
        with reading(self.home) as access:
            self._attached_artifact(access, ref, artifact)
        with mutation(self.home) as access:
            record = self._attached_artifact(access, ref, artifact)
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
