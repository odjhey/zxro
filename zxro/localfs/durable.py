import hashlib
import json
import os
import re
import uuid
from collections import OrderedDict
from datetime import datetime

from ..contract import Artifact, MailboxEvent, Settlement, Turn
from ..errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from ..ids import safe_string, validate_event_id, validate_id, validate_turn_id
from .home import check_stat
from ..settle import MAX_STDIN_BYTES, normalize_summary
from .ioutil import MAX_RECORD_BYTES, atomic_create, atomic_replace, locked_reading, mutation, read_json, reading


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")



class LocalDurableLoop:
    _ARTIFACT_CACHE_LIMIT = 256
    _artifact_envelope_cache = OrderedDict()

    def __init__(self, home, turns, registry=None, work=None):
        self.home, self.turns, self.registry, self.work = home, turns, registry, work

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
    def _artifact_identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    @staticmethod
    def _revalidate_artifact_identity(fd, directory_fd, filename, initial_info, path):
        """Require the scanned descriptor and current directory entry to agree."""
        try:
            current_fd_info = os.fstat(fd)
            current_path_info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise UnsafeStateError("artifact record changed during inspection") from exc
        except OSError as exc:
            raise UnsafeStateError("cannot revalidate artifact record identity") from exc
        check_stat(current_path_info, path, directory=False)
        initial_identity = LocalDurableLoop._artifact_identity(initial_info)
        if (LocalDurableLoop._artifact_identity(current_fd_info) != initial_identity
                or LocalDurableLoop._artifact_identity(current_path_info) != initial_identity):
            raise UnsafeStateError("artifact record changed during inspection")

    @staticmethod
    def _close_artifact_fd(fd, ref):
        try:
            os.close(fd)
        except OSError as exc:
            raise UnsafeStateError(f"cannot close artifact record: {ref}") from exc

    @staticmethod
    def _artifact_body_metadata(access, ref):
        """Read only the bounded metadata around an inline M1 artifact body."""
        turn_id, kind = Artifact.parse_ref(ref)
        filename = f"{turn_id}--{kind}.json"
        path = access.home / "artifacts" / filename
        try:
            with access.directory("artifacts") as directory_fd:
                try:
                    fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
                except FileNotFoundError:
                    raise NotFoundError(f"artifact record not found: {ref}") from None
                except OSError as exc:
                    raise UnsafeStateError(f"cannot open artifact record: {ref}") from exc
                try:
                    try:
                        info = os.fstat(fd)
                        check_stat(info, path, directory=False)
                        if info.st_size > MAX_RECORD_BYTES:
                            raise UnsafeStateError("artifact record is too large")
                        header = bytearray()
                        content_start = None
                        for offset in range(min(info.st_size, 512)):
                            header.extend(os.pread(fd, 1, offset))
                            if re.search(rb'"content_hex"\s*:\s*"$', header):
                                content_start = offset + 1
                                break
                        if content_start is None:
                            raise UnsafeStateError("invalid artifact record metadata")
                        if re.fullmatch(rb'\{\s*"bytes"\s*:\s*[0-9]+\s*,\s*"content_hex"\s*:\s*"', header) is None:
                            raise UnsafeStateError("invalid artifact record envelope")
                        bytes_match = re.search(rb'"bytes"\s*:\s*([0-9]+)', header)
                        if bytes_match is None:
                            raise UnsafeStateError("invalid artifact record metadata")
                        try:
                            body_bytes = int(bytes_match.group(1))
                        except ValueError as exc:
                            raise UnsafeStateError("invalid artifact record metadata") from exc
                        content_close = content_start + (body_bytes * 2)
                        if content_close >= info.st_size or os.pread(fd, 1, content_close) != b'"':
                            raise UnsafeStateError("invalid artifact record envelope")
                        metadata_start = content_close + 1
                        tail = os.pread(fd, min(info.st_size - metadata_start, 1024), metadata_start)
                        cache_key = (
                            str(access.home), filename, *LocalDurableLoop._artifact_identity(info)
                        )
                        cached = LocalDurableLoop._artifact_envelope_cache.pop(cache_key, None)
                        if cached is not None:
                            LocalDurableLoop._revalidate_artifact_identity(fd, directory_fd, filename, info, path)
                            LocalDurableLoop._artifact_envelope_cache[cache_key] = cached
                            return dict(cached)

                        header.decode("utf-8")
                        tail.decode("utf-8")

                        def scalar(segment, key):
                            match = re.search(rb'"' + key.encode("ascii") + rb'"\s*:\s*"([^"\r\n]*)"', segment)
                            try:
                                return match.group(1).decode("utf-8") if match else None
                            except UnicodeDecodeError as exc:
                                raise UnsafeStateError("invalid UTF-8 artifact metadata") from exc

                        value = {
                            "ref": scalar(tail, "ref"),
                            "turn_id": scalar(tail, "turn_id"),
                            "kind": scalar(tail, "kind"),
                            "bytes": body_bytes,
                            "sha256": scalar(tail, "sha256"),
                        }
                        if any(item is None for item in value.values()):
                            raise UnsafeStateError("invalid artifact record metadata")
                        expected_tail = (
                            ",\"kind\":" + json.dumps(value["kind"], separators=(",", ":"))
                            + ",\"ref\":" + json.dumps(value["ref"], separators=(",", ":"))
                            + ",\"sha256\":" + json.dumps(value["sha256"], separators=(",", ":"))
                            + ",\"turn_id\":" + json.dumps(value["turn_id"], separators=(",", ":"))
                            + "}"
                        ).encode("utf-8")
                        if tail.rstrip(b" \t\r\n") != expected_tail:
                            raise UnsafeStateError("invalid artifact record envelope")
                        trailing_start = metadata_start + len(expected_tail)
                        offset = trailing_start
                        while offset < info.st_size:
                            chunk = os.pread(fd, min(64 * 1024, info.st_size - offset), offset)
                            if not chunk or any(byte not in b" \t\r\n" for byte in chunk):
                                raise UnsafeStateError("invalid trailing artifact record bytes")
                            offset += len(chunk)
                        LocalDurableLoop._revalidate_artifact_identity(fd, directory_fd, filename, info, path)
                        try:
                            parsed = Artifact.parse_ref(value["ref"])
                            digest = bytes.fromhex(value["sha256"])
                            if parsed != (turn_id, kind) or value["turn_id"] != turn_id or value["kind"] != kind:
                                raise ValueError("artifact identity mismatch")
                            if type(value["bytes"]) is not int or value["bytes"] < 0 or len(digest) != 32 or len(value["sha256"]) != 64:
                                raise ValueError("artifact metadata bounds")
                        except (TypeError, ValueError, ValidationError) as exc:
                            raise UnsafeStateError("invalid artifact record metadata") from exc
                        cache = LocalDurableLoop._artifact_envelope_cache
                        cache[cache_key] = dict(value)
                        while len(cache) > LocalDurableLoop._ARTIFACT_CACHE_LIMIT:
                            cache.popitem(last=False)
                        return value
                    except UnicodeDecodeError as exc:
                        raise UnsafeStateError("invalid UTF-8 artifact metadata") from exc
                    except OSError as exc:
                        raise UnsafeStateError(f"cannot inspect artifact record: {ref}") from exc
                finally:
                    LocalDurableLoop._close_artifact_fd(fd, ref)
        except FileNotFoundError:
            raise NotFoundError(f"artifact record not found: {ref}") from None
        except OSError as exc:
            raise UnsafeStateError(f"cannot inspect artifact record: {ref}") from exc

    @staticmethod
    def _artifact_metadata(access, ref, cache=None):
        if cache is not None and ref in cache:
            return cache[ref]
        body = LocalDurableLoop._artifact_body_metadata(access, ref)
        turn_id, kind = Artifact.parse_ref(ref)
        try:
            sidecar = read_json(access, "artifact-metadata", f"{turn_id}--{kind}.json")
        except NotFoundError:
            value = body
        else:
            required = {"ref", "turn_id", "kind", "bytes", "sha256"}
            try:
                parsed = Artifact.parse_ref(sidecar.get("ref"))
                digest = bytes.fromhex(sidecar.get("sha256", ""))
                valid = set(sidecar) == required
                valid = valid and parsed == (turn_id, kind)
                valid = valid and sidecar.get("turn_id") == turn_id and sidecar.get("kind") == kind
                valid = valid and type(sidecar.get("bytes")) is int and sidecar["bytes"] >= 0
                valid = valid and len(digest) == 32 and len(sidecar["sha256"]) == 64
            except (TypeError, ValueError, ValidationError) as exc:
                raise UnsafeStateError("invalid artifact metadata") from exc
            if not valid or sidecar != body:
                raise UnsafeStateError("artifact metadata does not match artifact record")
            value = sidecar
        if cache is not None:
            cache[ref] = value
        return value

    def _validate_event(self, access, event, *, metadata_only=False, artifact_cache=None):
        try:
            turn = self.turns.get_from(access, event.turn_id)
        except NotFoundError as exc:
            raise UnsafeStateError("mailbox event references missing turn") from exc
        expected = MailboxEvent(turn.settlement.event_id, event.generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at) if turn.state == "settled" else None
        if expected != event:
            raise UnsafeStateError("mailbox event does not match terminal turn")
        for ref in event.artifact_refs:
            try:
                artifact = self._artifact_metadata(access, ref, artifact_cache)
            except NotFoundError as exc:
                raise UnsafeStateError("mailbox event references missing artifact") from exc
            if artifact["ref"] != ref or artifact["turn_id"] != event.turn_id or artifact["sha256"] != turn.settlement.payload_sha256:
                raise UnsafeStateError("mailbox event artifact does not match durable settlement metadata")
        return event

    def _artifact_summary_for_turn(self, access, turn, artifact_cache=None):
        total_bytes = 0
        for ref in turn.artifact_refs:
            try:
                artifact = self._artifact_metadata(access, ref, artifact_cache)
            except NotFoundError as exc:
                raise UnsafeStateError("turn references missing artifact") from exc
            if turn.settlement is None or artifact["sha256"] != turn.settlement.payload_sha256:
                raise UnsafeStateError("turn artifact metadata does not match settlement")
            total_bytes += artifact["bytes"]
        return len(turn.artifact_refs), total_bytes

    def _read_only_unread_count(self, access, watchtower_id, artifact_cache=None):
        box = self._mailbox(access, watchtower_id)
        try:
            events = [self._event(access, watchtower_id, generation) for generation in range(box["ack"] + 1, box["highest"] + 1)]
            for event in events:
                self._validate_index(access, event)
                self._validate_event(access, event, metadata_only=True, artifact_cache=artifact_cache)
        except NotFoundError as exc:
            raise UnsafeStateError("mailbox index references missing event or artifact metadata") from exc
        return len(events)

    def _read_only_pending_count(self, access, watchtower_id, artifact_cache=None):
        box = self._mailbox(access, watchtower_id)
        resolved = []
        seen = set()
        for event_id in box["unresolved"]:
            if event_id in seen:
                continue
            seen.add(event_id)
            resolved.append(event_id)
        try:
            unseen = [self._event_by_id(access, event_id) for event_id in resolved]
            for event in unseen:
                self._validate_index(access, event)
                self._validate_event(access, event, metadata_only=True, artifact_cache=artifact_cache)
        except NotFoundError as exc:
            raise UnsafeStateError("mailbox index references missing event or artifact metadata") from exc
        return sum(1 for event in unseen if self._handled(access, event) is None)

    def inspect(self, work_id):
        work_id = validate_id(work_id, "work id")
        artifact_cache = {}
        with locked_reading(self.home) as access:
            work = self.work.get_from(access, work_id)
            if self.registry is not None:
                watchtower = self.registry.get_from(access, work.watchtower_id)
            else:
                watchtower = type("Watchtower", (), {"id": work.watchtower_id, "cwd": ""})
            turns = self.turns.list_from(access, work_id)
            unread_count = self._read_only_unread_count(access, work.watchtower_id, artifact_cache)
            pending_count = self._read_only_pending_count(access, work.watchtower_id, artifact_cache)
            box = self._mailbox(access, work.watchtower_id)
            summary = {
                "work": {
                    "id": work.id,
                    "watchtower_id": work.watchtower_id,
                    "state": work.state,
                },
                "watchtower": {
                    "id": watchtower.id,
                    "cwd": watchtower.cwd,
                },
                "inbox": {
                    "highest_generation": box["highest"],
                    "read_ack_generation": box["ack"],
                    "unread_count": unread_count,
                    "pending_attention_count": pending_count,
                },
                "turns": [],
            }
            for item in turns:
                artifact_count, artifact_bytes = self._artifact_summary_for_turn(access, item, artifact_cache)
                summary["turns"].append({
                    "id": item.id,
                    "agent": item.agent,
                    "session": item.session,
                    "cwd": item.cwd,
                    "state": item.state,
                    "artifact_count": artifact_count,
                    "artifact_bytes": artifact_bytes,
                })
            return summary

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

    def settle(self, turn_id, source, outcome, message, payload):
        turn_id = validate_turn_id(turn_id)
        source = safe_string(source, "source")
        if outcome not in {"completed", "failed", "cancelled"}:
            raise ValidationError(f"invalid settlement status: {outcome!r}")
        message = normalize_summary(message)
        if payload is not None and len(payload) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        digest = hashlib.sha256(payload).hexdigest() if payload is not None else None
        with reading(self.home) as access:
            self.turns.get_from(access, turn_id)
        with mutation(self.home) as access:
            turn = self.turns.get_from(access, turn_id)
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
                artifact_refs = ()
                if payload is not None:
                    ref = f"artifact:{turn_id}:stdin"
                    artifact = Artifact(ref, turn_id, "stdin", len(payload), digest, payload.hex()).to_dict()
                    encoded_size = len((json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
                    if encoded_size > MAX_RECORD_BYTES:
                        raise ValidationError(f"stdin payload too large to store as a durable artifact: {len(payload)} bytes")
                    atomic_replace(access, "artifacts", f"{turn_id}--stdin.json", artifact)
                    atomic_replace(
                        access,
                        "artifact-metadata",
                        f"{turn_id}--stdin.json",
                        {key: artifact[key] for key in ("ref", "turn_id", "kind", "bytes", "sha256")},
                    )
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
                expected = MailboxEvent(turn.settlement.event_id, event.generation, "turn_settled", turn.watchtower_id, turn.work_id, turn.id, turn.agent, turn.outcome, turn.summary, turn.artifact_refs, turn.settlement.settled_at)
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
