import hashlib
import json
import os
import time
from dataclasses import replace
from pathlib import Path

from zxro.contract import Work, WorkBrief
from zxro.errors import ConflictError, NotFoundError, UnsafeStateError, ValidationError
from zxro.ids import validate_id
from zxro.metadata import RESERVED_NAMESPACES, validate_metadata, validate_name, validate_namespace
from zxro.settle import MAX_STDIN_BYTES
from .home import check_stat
from .ioutil import MAX_RECORD_BYTES, atomic_create, atomic_replace, exact_record_is_durable, list_records, mutation, read_json, reading


class LocalWorkStore:
    def __init__(self, home: Path, registry):
        self.home, self.registry = home, registry
        self.diagnostic_observer = None

    @staticmethod
    def _durable(record):
        value = record.to_dict()
        if record.brief is not None:
            value["brief"] = record.brief.to_dict()
        return value

    @staticmethod
    def _brief_ref(work_id):
        return f"artifact:work:{work_id}:brief"

    @staticmethod
    def _brief_name(work_id):
        return f"work--{work_id}--brief.json"

    @classmethod
    def _brief_value(cls, work_id, payload):
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "ref": cls._brief_ref(work_id), "work_id": work_id, "kind": "brief",
            "bytes": len(payload), "sha256": digest, "content_hex": payload.hex(),
        }

    @classmethod
    def _decode_brief_artifact(cls, value, work_id):
        required = {"ref", "work_id", "kind", "bytes", "sha256", "content_hex"}
        try:
            content = bytes.fromhex(value["content_hex"])
            valid = set(value) == required and value["ref"] == cls._brief_ref(work_id)
            valid = valid and value["work_id"] == work_id and value["kind"] == "brief"
            valid = valid and type(value["bytes"]) is int and value["bytes"] >= 0
            valid = valid and value["bytes"] == len(content)
            valid = valid and hashlib.sha256(content).hexdigest() == value["sha256"]
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise UnsafeStateError("invalid work brief artifact record")
        return value

    @classmethod
    def _brief_record(cls, access, work_id):
        return cls._decode_brief_artifact(read_json(access, "artifacts", cls._brief_name(work_id)), work_id)

    @classmethod
    def _write_brief_artifact(cls, access, work_id, payload):
        if len(payload) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        value = cls._brief_value(work_id, payload)
        encoded_size = len((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
        if encoded_size > MAX_RECORD_BYTES:
            raise ValidationError(f"stdin payload too large to store as a durable artifact: {len(payload)} bytes")
        try:
            atomic_create(access, "artifacts", cls._brief_name(work_id), value)
        except ConflictError:
            existing = cls._brief_record(access, work_id)
            if existing != value:
                raise ConflictError(f"work brief retry has different content: {work_id}")
        if os.environ.get("ZXRO_FAULT_EXIT_AFTER") == "artifact-commit":
            os._exit(86)
        return WorkBrief(value["ref"], value["bytes"], value["sha256"])

    def create(self, id, watchtower_id, brief=None):
        id, watchtower_id = validate_id(id, "work id"), validate_id(watchtower_id, "watchtower id")
        if brief is not None and len(brief) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        self.registry.get(watchtower_id)
        with mutation(self.home) as access:
            self.registry.get_from(access, watchtower_id)
            try:
                read_json(access, "work", f"{id}.json")
            except NotFoundError:
                pass
            else:
                raise ConflictError(f"work already exists: {id}")
            brief_metadata = self._write_brief_artifact(access, id, brief) if brief is not None else None
            record = Work(id, watchtower_id, "open", brief=brief_metadata)
            durable = self._durable(record)
            try:
                atomic_create(access, "work", f"{id}.json", durable)
            except Exception:
                if not exact_record_is_durable(access, "work", f"{id}.json", durable):
                    raise
        return record

    def get(self, id):
        id = validate_id(id, "work id")
        with reading(self.home) as access:
            return self.get_from(access, id)

    def get_from(self, access, id):
        record = self._decode(read_json(access, "work", f"{id}.json"))
        try:
            self.registry.get_from(access, record.watchtower_id)
        except Exception as exc:
            raise UnsafeStateError(f"invalid work ownership: {exc}") from exc
        return record

    def list(self, watchtower_id=None, state=None):
        if watchtower_id is not None:
            validate_id(watchtower_id, "watchtower id")
        if state is not None and state not in ("open", "closed"):
            raise ValidationError(f"invalid work state: {state!r}")
        try:
            with reading(self.home) as access:
                records = [self._decode(item) for item in list_records(access, "work")]
                for record in records:
                    try:
                        self.registry.get_from(access, record.watchtower_id)
                    except Exception as exc:
                        raise UnsafeStateError(f"invalid work ownership: {exc}") from exc
        except NotFoundError:
            return []
        return sorted((item for item in records if (watchtower_id is None or item.watchtower_id == watchtower_id) and (state is None or item.state == state)), key=lambda item: item.id)

    def close(self, id):
        id = validate_id(id, "work id")
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            if current.state == "closed":
                return current
            closed = replace(current, state="closed")
            atomic_replace(access, "work", f"{id}.json", self._durable(closed))
            return closed

    def set_brief(self, id, payload):
        id = validate_id(id, "work id")
        if len(payload) > MAX_STDIN_BYTES:
            raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            if current.state != "open":
                raise ConflictError(f"cannot set brief for closed work: {id}")
            if current.brief is not None:
                raise ConflictError(f"work brief already exists: {id}")
            metadata = self._write_brief_artifact(access, id, payload)
            updated = replace(current, brief=metadata)
            durable = self._durable(updated)
            try:
                atomic_replace(access, "work", f"{id}.json", durable)
            except Exception:
                if not exact_record_is_durable(access, "work", f"{id}.json", durable):
                    raise
            return updated

    def brief_path(self, id):
        observer = self.diagnostic_observer
        clock = getattr(observer, "_clock", time.monotonic)
        started = clock()
        try:
            result = self._verified_brief_path(id)
        except BaseException as exc:
            if observer is not None:
                try:
                    observer.artifact_verification(False, (clock() - started) * 1000, exc)
                except Exception:
                    pass
            raise
        if observer is not None:
            try:
                observer.artifact_verification(True, (clock() - started) * 1000)
            except Exception:
                pass
        return result

    def _verified_brief_path(self, id):
        id = validate_id(id, "work id")
        with reading(self.home) as access:
            work = self.get_from(access, id)
            if work.brief is None:
                raise NotFoundError(f"work brief not found: {id}")
        with mutation(self.home) as access:
            work = self.get_from(access, id)
            if work.brief is None:
                raise NotFoundError(f"work brief not found: {id}")
            record = self._brief_record(access, id)
            expected = WorkBrief(record["ref"], record["bytes"], record["sha256"])
            if work.brief != expected:
                raise UnsafeStateError("work brief does not match attached artifact")
            filename = f"work--{id}--brief.bin"
            path = self.home / "artifacts" / filename
            content = bytes.fromhex(record["content_hex"])
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
                    if info.st_nlink != 1:
                        raise UnsafeStateError("work brief materialization has multiple links")
                    if info.st_mode & 0o222:
                        raise UnsafeStateError("work brief materialization is writable")
                    os.lseek(fd, 0, os.SEEK_SET)
                    chunks = []
                    remaining = work.brief.bytes + 1
                    while remaining:
                        chunk = os.read(fd, min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    actual = b"".join(chunks)
                    entry = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
                    check_stat(entry, path, directory=False)
                    if entry.st_nlink != 1:
                        raise UnsafeStateError("work brief materialization has multiple links")
                    if (entry.st_dev, entry.st_ino) != (info.st_dev, info.st_ino):
                        raise UnsafeStateError("work brief path changed during verification")
                except OSError as exc:
                    raise UnsafeStateError(f"cannot verify work brief path: {exc}") from exc
                finally:
                    if fd is not None:
                        os.close(fd)
                if len(actual) != work.brief.bytes or hashlib.sha256(actual).hexdigest() != work.brief.sha256:
                    raise UnsafeStateError("work brief path does not match durable content")
            return {"ref": work.brief.ref, "path": str(path), "bytes": work.brief.bytes}

    def set_metadata(self, id, namespace, payload):
        id = validate_id(id, "work id")
        payload = validate_namespace(namespace, payload)
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            metadata = dict(current.metadata or {})
            metadata[namespace] = payload
            updated = replace(current, metadata=validate_metadata(metadata))
            atomic_replace(access, "work", f"{id}.json", self._durable(updated))
            return updated

    def unset_metadata(self, id, namespace):
        id = validate_id(id, "work id")
        validate_name(namespace, "metadata namespace")
        if namespace in RESERVED_NAMESPACES:
            raise ValidationError(f"reserved metadata namespace: {namespace}")
        with mutation(self.home) as access:
            current = self.get_from(access, id)
            if not current.metadata or namespace not in current.metadata:
                return current
            metadata = dict(current.metadata)
            del metadata[namespace]
            updated = replace(current, metadata=metadata or None)
            atomic_replace(access, "work", f"{id}.json", self._durable(updated))
            return updated

    @staticmethod
    def _decode(data):
        allowed = {"id", "watchtower_id", "state", "metadata", "brief"}
        if not {"id", "watchtower_id", "state"} <= set(data) or set(data) - allowed or not all(isinstance(data.get(key), str) for key in ("id", "watchtower_id", "state")) or data.get("state") not in ("open", "closed") or data.get("metadata", {}) is None:
            raise UnsafeStateError("invalid work record schema")
        try:
            validate_id(data["id"], "work id")
            validate_id(data["watchtower_id"], "watchtower id")
            metadata = validate_metadata(data.get("metadata", {}), normalize=False)
            brief = None
            if "brief" in data:
                value = data["brief"]
                digest = value.get("sha256") if isinstance(value, dict) else None
                if set(value) != {"ref", "bytes", "sha256"} or value["ref"] != LocalWorkStore._brief_ref(data["id"]) or type(value["bytes"]) is not int or not 0 <= value["bytes"] <= MAX_STDIN_BYTES or not isinstance(digest, str) or len(digest) != 64 or bytes.fromhex(digest).hex() != digest:
                    raise ValueError("invalid brief metadata")
                brief = WorkBrief(**value)
        except Exception as exc:
            raise UnsafeStateError(f"invalid work record: {exc}") from exc
        return Work(data["id"], data["watchtower_id"], data["state"], metadata or None, brief)
