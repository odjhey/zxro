import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from zxro.errors import ConflictError, NotFoundError, UnsafeStateError
from .home import check_owned_mode, ensure_layout, prepare_home


@contextmanager
def mutation(home: Path):
    prepare_home(home)
    lock_path = home / ".lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    existed = lock_path.exists() or lock_path.is_symlink()
    if existed:
        check_owned_mode(lock_path, directory=False)
    try:
        fd = os.open(lock_path, flags, 0o600)
        if not existed:
            os.fchmod(fd, 0o600)
    except OSError as exc:
        raise UnsafeStateError(f"cannot open store lock: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise UnsafeStateError("unsafe store lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        ensure_layout(home)
        yield
    finally:
        os.close(fd)


def require_layout(home: Path) -> None:
    prepare_home(home)
    ensure_layout(home)
    lock = home / ".lock"
    if lock.exists() or lock.is_symlink():
        check_owned_mode(lock, directory=False)


def read_json(path: Path) -> dict:
    if not path.parent.exists() and not path.parent.is_symlink():
        raise NotFoundError(f"record not found: {path.stem}")
    check_owned_mode(path.parent, directory=True)
    if not path.exists() and not path.is_symlink():
        raise NotFoundError(f"record not found: {path.stem}")
    check_owned_mode(path, directory=False)
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UnsafeStateError(f"malformed state record {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UnsafeStateError(f"state record is not an object: {path}")
    if path.suffix == ".json" and isinstance(value.get("id"), str) and value["id"] != path.stem:
        raise UnsafeStateError(f"record identity does not match its path: {path}")
    return value


def atomic_create(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise UnsafeStateError(f"unsafe record path: {path}")
        read_json(path)
        raise ConflictError(f"record already exists: {path.stem}")
    atomic_replace(path, value)


def atomic_replace(path: Path, value: dict) -> None:
    check_owned_mode(path.parent, directory=True)
    fd, temporary = tempfile.mkstemp(prefix=".zxro-tmp-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def list_records(directory: Path) -> list[dict]:
    check_owned_mode(directory, directory=True)
    records = []
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise UnsafeStateError(f"cannot list state directory {directory}: {exc}") from exc
    for entry in entries:
        if entry.name.startswith(".zxro-tmp-"):
            continue
        if entry.suffix != ".json":
            raise UnsafeStateError(f"unexpected state entry: {entry}")
        records.append(read_json(entry))
    return records
