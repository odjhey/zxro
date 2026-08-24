import fcntl
import json
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from zxro.errors import ConflictError, NotFoundError, UnsafeStateError
from .home import MANAGED_DIRS, check_stat, prepare_home

_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_RECORD_FLAGS = os.O_RDONLY | _NOFOLLOW | _NONBLOCK
MAX_RECORD_BYTES = 16 * 1024 * 1024


def _same_inode(left, right):
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


class StoreAccess:
    def __init__(self, home: Path, *, create: bool = False):
        self.home = home
        self.create = create
        self.home_fd = None

    def __enter__(self):
        if self.create:
            prepare_home(self.home)
        try:
            before = self.home.lstat()
            check_stat(before, self.home, directory=True)
            self.home_fd = os.open(self.home, _DIRECTORY_FLAGS)
            current = os.fstat(self.home_fd)
            check_stat(current, self.home, directory=True)
            if not _same_inode(before, current):
                raise UnsafeStateError(f"state path changed while opening: {self.home}")
            self.verify_home()
            return self
        except BaseException as exc:
            if self.home_fd is not None:
                os.close(self.home_fd)
                self.home_fd = None
            if isinstance(exc, FileNotFoundError):
                raise NotFoundError("zxro home does not exist") from None
            if isinstance(exc, UnsafeStateError):
                raise
            if isinstance(exc, OSError):
                raise UnsafeStateError(f"cannot open zxro home {self.home}: {exc}") from exc
            raise

    def __exit__(self, *_):
        if self.home_fd is not None:
            os.close(self.home_fd)

    def verify_home(self):
        try:
            path_stat = self.home.lstat()
            fd_stat = os.fstat(self.home_fd)
        except OSError as exc:
            raise UnsafeStateError(f"cannot verify zxro home {self.home}: {exc}") from exc
        check_stat(path_stat, self.home, directory=True)
        check_stat(fd_stat, self.home, directory=True)
        if not _same_inode(path_stat, fd_stat):
            raise UnsafeStateError(f"zxro home changed during operation: {self.home}")

    def ensure_layout(self):
        for name in MANAGED_DIRS:
            try:
                os.mkdir(name, 0o700, dir_fd=self.home_fd)
            except FileExistsError:
                pass
            with self.directory(name):
                pass

    @contextmanager
    def directory(self, name):
        self.verify_home()
        fd = None
        try:
            before = os.stat(name, dir_fd=self.home_fd, follow_symlinks=False)
            check_stat(before, self.home / name, directory=True)
            fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=self.home_fd)
            current = os.fstat(fd)
            check_stat(current, self.home / name, directory=True)
            if not _same_inode(before, current):
                raise UnsafeStateError(f"managed directory changed while opening: {self.home / name}")
        except FileNotFoundError:
            if fd is not None:
                os.close(fd)
            raise NotFoundError(f"managed directory does not exist: {name}") from None
        except BaseException as exc:
            if fd is not None:
                os.close(fd)
            if isinstance(exc, UnsafeStateError):
                raise
            if isinstance(exc, OSError):
                raise UnsafeStateError(f"cannot open managed directory {self.home / name}: {exc}") from exc
            raise
        try:
            yield fd
            self.verify_directory(name, fd)
        finally:
            os.close(fd)

    def verify_directory(self, name, fd):
        self.verify_home()
        try:
            path_stat = os.stat(name, dir_fd=self.home_fd, follow_symlinks=False)
            fd_stat = os.fstat(fd)
        except OSError as exc:
            raise UnsafeStateError(f"cannot verify managed directory {self.home / name}: {exc}") from exc
        check_stat(path_stat, self.home / name, directory=True)
        check_stat(fd_stat, self.home / name, directory=True)
        if not _same_inode(path_stat, fd_stat):
            raise UnsafeStateError(f"managed directory changed during operation: {self.home / name}")


@contextmanager
def reading(home: Path):
    with StoreAccess(home) as access:
        yield access


@contextmanager
def mutation(home: Path):
    with StoreAccess(home, create=True) as access:
        flags = os.O_RDWR | os.O_CREAT | _NOFOLLOW
        try:
            existed = True
            try:
                lock_before = os.stat(".lock", dir_fd=access.home_fd, follow_symlinks=False)
            except FileNotFoundError:
                existed = False
                lock_before = None
            fd = os.open(".lock", flags, 0o600, dir_fd=access.home_fd)
            if not existed:
                os.fchmod(fd, 0o600)
            lock_stat = os.fstat(fd)
            check_stat(lock_stat, access.home / ".lock", directory=False)
            if lock_before is not None:
                check_stat(lock_before, access.home / ".lock", directory=False)
                if not _same_inode(lock_before, lock_stat):
                    raise UnsafeStateError("store lock changed while opening")
            fcntl.flock(fd, fcntl.LOCK_EX)
            _verify_lock(access, fd, lock_stat)
            access.ensure_layout()
            yield access
            _verify_lock(access, fd, lock_stat)
        except OSError as exc:
            raise UnsafeStateError(f"cannot use store lock: {exc}") from exc
        finally:
            if "fd" in locals():
                os.close(fd)


def _verify_lock(access, fd, expected):
    access.verify_home()
    try:
        path_stat = os.stat(".lock", dir_fd=access.home_fd, follow_symlinks=False)
        fd_stat = os.fstat(fd)
    except OSError as exc:
        raise UnsafeStateError(f"cannot verify store lock: {exc}") from exc
    check_stat(path_stat, access.home / ".lock", directory=False)
    check_stat(fd_stat, access.home / ".lock", directory=False)
    if not _same_inode(path_stat, fd_stat) or not _same_inode(expected, fd_stat):
        raise UnsafeStateError("store lock changed during operation")


def _check_record_fd(fd: int, label: Path, *, readonly: bool = False, mode: int | None = None):
    try:
        current = os.fstat(fd)
    except OSError as exc:
        raise UnsafeStateError(f"cannot inspect state record {label}: {exc}") from exc
    check_stat(current, label, directory=False)
    if readonly and current.st_mode & 0o222:
        raise UnsafeStateError(f"state record is writable: {label}")
    if mode is not None and stat.S_IMODE(current.st_mode) != mode:
        raise UnsafeStateError(f"state record mode changed: {label}")
    return current


def _open_record(directory_fd: int, filename: str, label: Path, *, readonly: bool = False, mode: int | None = None) -> int:
    fd = None
    try:
        fd = os.open(filename, _RECORD_FLAGS, dir_fd=directory_fd)
        _check_record_fd(fd, label, readonly=readonly, mode=mode)
        return fd
    except BaseException as exc:
        if fd is not None:
            os.close(fd)
        if isinstance(exc, FileNotFoundError):
            raise NotFoundError(f"record not found: {Path(filename).stem}") from None
        if isinstance(exc, UnsafeStateError):
            raise
        if isinstance(exc, OSError):
            raise UnsafeStateError(f"cannot open state record {label}: {exc}") from exc
        raise


def _sample_chain(access, directory: str, filename: str, *, readonly: bool, mode: int | None = None):
    """Open one ordered namespace sample. Each open is its lookup checkpoint."""
    home_fd = directory_fd = record_fd = None
    label = access.home / directory / filename
    try:
        home_fd = os.open(access.home, _DIRECTORY_FLAGS)
        home_stat = os.fstat(home_fd)
        check_stat(home_stat, access.home, directory=True)
        if not _same_inode(home_stat, os.fstat(access.home_fd)):
            raise UnsafeStateError(f"zxro home changed during operation: {access.home}")
        directory_fd = os.open(directory, _DIRECTORY_FLAGS, dir_fd=home_fd)
        directory_stat = os.fstat(directory_fd)
        check_stat(directory_stat, access.home / directory, directory=True)
        record_fd = _open_record(directory_fd, filename, label, readonly=readonly, mode=mode)
        return home_fd, directory_fd, record_fd
    except BaseException as exc:
        for fd in (record_fd, directory_fd, home_fd):
            if fd is not None:
                os.close(fd)
        if isinstance(exc, NotFoundError):
            raise
        if isinstance(exc, (UnsafeStateError, OSError)):
            if isinstance(exc, UnsafeStateError):
                raise
            raise UnsafeStateError(f"cannot sample state record {label}: {exc}") from exc
        raise


def _read_bounded(fd: int, max_bytes: int, label: Path) -> bytes:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - size))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise UnsafeStateError(f"state record is too large: {label}")
    except UnsafeStateError:
        raise
    except OSError as exc:
        raise UnsafeStateError(f"cannot read state record {label}: {exc}") from exc


def _parse_object(raw: bytes, label: Path) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UnsafeStateError(f"malformed state record {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise UnsafeStateError(f"state record is not an object: {label}")
    return value


class PinnedRecord:
    def __init__(self, access, directory, filename, directory_fd, record_fd, value, raw, readonly, max_bytes, mode=None):
        self.value = value
        self.raw = raw
        self.directory_fd = directory_fd
        self.record_fd = record_fd
        self._access = access
        self._directory = directory
        self._filename = filename
        self._label = access.home / directory / filename
        self._readonly = readonly
        self._max_bytes = max_bytes
        self._mode = mode

    def verify_current(self) -> None:
        try:
            sample = _sample_chain(
                self._access, self._directory, self._filename, readonly=self._readonly, mode=self._mode
            )
        except NotFoundError:
            raise UnsafeStateError(f"state record changed during operation: {self._label}") from None
        try:
            _, sampled_directory_fd, sampled_record_fd = sample
            if not _same_inode(os.fstat(sampled_directory_fd), os.fstat(self.directory_fd)):
                raise UnsafeStateError(f"managed directory changed during operation: {self._label.parent}")
            if not _same_inode(os.fstat(sampled_record_fd), os.fstat(self.record_fd)):
                raise UnsafeStateError(f"state record changed during operation: {self._label}")
            before = _check_record_fd(sampled_record_fd, self._label, readonly=self._readonly, mode=self._mode)
            if _read_bounded(sampled_record_fd, self._max_bytes, self._label) != self.raw:
                raise UnsafeStateError(f"state record contents changed during operation: {self._label}")
            after = _check_record_fd(sampled_record_fd, self._label, readonly=self._readonly, mode=self._mode)
            if not _same_inode(before, after):
                raise UnsafeStateError(f"state record changed during operation: {self._label}")
        finally:
            for fd in reversed(sample):
                os.close(fd)


class PinnedRecordSet:
    def __init__(self):
        self._pins = []

    def add(self, pin: PinnedRecord) -> None:
        self._pins.append(pin)

    def verify_current(self) -> None:
        for pin in self._pins:
            pin.verify_current()


def _check_record_identity(value: dict, filename: str, label: Path) -> dict:
    if filename.endswith(".json") and isinstance(value.get("id"), str) and value["id"] != Path(filename).stem:
        raise UnsafeStateError(f"record identity does not match its path: {label}")
    return value


@contextmanager
def open_json_pinned(access: StoreAccess, directory: str, filename: str, *, readonly: bool = False, max_bytes: int = MAX_RECORD_BYTES) -> Iterator[PinnedRecord]:
    label = access.home / directory / filename
    with access.directory(directory) as directory_fd:
        record_fd = _open_record(directory_fd, filename, label, readonly=readonly)
        try:
            _check_record_fd(record_fd, label, readonly=readonly)
            raw = _read_bounded(record_fd, max_bytes, label)
            value = _check_record_identity(_parse_object(raw, label), filename, label)
            pin = PinnedRecord(access, directory, filename, directory_fd, record_fd, value, raw, readonly, max_bytes)
            pin.verify_current()
            yield pin
            pin.verify_current()
        finally:
            os.close(record_fd)


@contextmanager
def read_json_pinned(access: StoreAccess, directory: str, filename: str, *, readonly: bool = False, max_bytes: int = MAX_RECORD_BYTES):
    with open_json_pinned(access, directory, filename, readonly=readonly, max_bytes=max_bytes) as pin:
        yield pin.value


def read_json(access: StoreAccess, directory: str, filename: str) -> dict:
    with open_json_pinned(access, directory, filename) as pin:
        return pin.value


def _encoded(value: dict, label: Path) -> bytes:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(payload) > MAX_RECORD_BYTES:
        raise UnsafeStateError(f"state record is too large: {label}")
    return payload


def _remove_temp(directory_fd: int, temporary: str) -> None:
    """Best-effort direct cleanup after no mismatch was observed.

    A sample is only an observation. It is not bound to this unlink. Direct
    unlink may remove a same-UID replacement installed after that observation.
    """
    try:
        os.unlink(temporary, dir_fd=directory_fd)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise UnsafeStateError(f"cannot remove temporary publication path {temporary}: {exc}") from exc


def _temp_name_is_current(directory_fd: int, temporary: str, temp_fd: int, label: Path, *, mode: int) -> bool:
    sample_fd = None
    try:
        sample_fd = _open_record(directory_fd, temporary, label, readonly=not bool(mode & 0o222), mode=mode)
        return _same_inode(os.fstat(sample_fd), os.fstat(temp_fd))
    except (NotFoundError, UnsafeStateError, OSError):
        return False
    finally:
        if sample_fd is not None:
            os.close(sample_fd)


class _PublishedIndeterminate(UnsafeStateError):
    pass


def _raise_indeterminate(label: Path, exc: BaseException):
    if isinstance(exc, _PublishedIndeterminate):
        raise exc
    raise _PublishedIndeterminate(f"state record may have been published: {label}") from exc


@contextmanager
def publish_json_exact_pinned(access: StoreAccess, directory: str, filename: str, expected: dict, *, validate: Callable[[dict], dict], mode: int = 0o400, _accept_existing: bool = True) -> Iterator[PinnedRecord]:
    label = access.home / directory / filename
    normalized = validate(expected)
    payload = _encoded(expected, label)
    readonly = not bool(mode & 0o222)
    with access.directory(directory) as directory_fd:
        temporary = f".zxro-tmp-{secrets.token_hex(16)}"
        temp_fd = sample_fd = record_fd = None
        destination_created = False
        cleanup_temp = False
        try:
            temp_fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=directory_fd)
            cleanup_temp = True
            os.fchmod(temp_fd, mode)
            view = memoryview(payload)
            while view:
                written = os.write(temp_fd, view)
                if written <= 0:
                    raise UnsafeStateError(f"cannot write state record {label}")
                view = view[written:]
            os.fsync(temp_fd)
            before = _check_record_fd(temp_fd, label, readonly=readonly, mode=mode)
            if _read_bounded(temp_fd, MAX_RECORD_BYTES, label) != payload:
                raise UnsafeStateError(f"temporary state record changed during publication: {label}")
            _check_record_fd(temp_fd, label, readonly=readonly, mode=mode)

            cleanup_temp = False
            sample_fd = _open_record(directory_fd, temporary, label, readonly=readonly, mode=mode)
            if not _same_inode(os.fstat(sample_fd), before):
                raise UnsafeStateError(f"temporary state record changed during publication: {label}")
            os.close(sample_fd)
            sample_fd = None
            cleanup_temp = False
            try:
                os.link(temporary, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
                destination_created = True
            except FileExistsError:
                cleanup_temp = _temp_name_is_current(directory_fd, temporary, temp_fd, label, mode=mode)
                if cleanup_temp:
                    _remove_temp(directory_fd, temporary)
                    cleanup_temp = False
                try:
                    record_fd = _open_record(directory_fd, filename, label, readonly=readonly, mode=mode)
                except NotFoundError:
                    raise UnsafeStateError(f"state record changed during publication: {label}") from None
            except BaseException:
                cleanup_temp = _temp_name_is_current(directory_fd, temporary, temp_fd, label, mode=mode)
                raise
            else:
                try:
                    cleanup_temp = _temp_name_is_current(directory_fd, temporary, temp_fd, label, mode=mode)
                    record_fd = _open_record(directory_fd, filename, label, readonly=readonly, mode=mode)
                    if not _same_inode(os.fstat(record_fd), os.fstat(temp_fd)):
                        raise UnsafeStateError(f"published state record changed during operation: {label}")
                    raw = _read_bounded(record_fd, MAX_RECORD_BYTES, label)
                    if raw != payload:
                        raise UnsafeStateError(f"published state record changed during operation: {label}")
                    _check_record_fd(record_fd, label, readonly=readonly, mode=mode)
                    if cleanup_temp:
                        _remove_temp(directory_fd, temporary)
                        cleanup_temp = False
                    os.fsync(directory_fd)
                    raw = _read_bounded(record_fd, MAX_RECORD_BYTES, label)
                    value = _check_record_identity(_parse_object(raw, label), filename, label)
                    existing_normalized = validate(value)
                    if existing_normalized != normalized:
                        raise UnsafeStateError(f"published state record validation mismatch: {label}")
                    pin = PinnedRecord(access, directory, filename, directory_fd, record_fd, value, raw, readonly, MAX_RECORD_BYTES, mode=mode)
                    pin.verify_current()
                    yield pin
                    pin.verify_current()
                    return
                except BaseException as exc:
                    _raise_indeterminate(label, exc)

            raw = _read_bounded(record_fd, MAX_RECORD_BYTES, label)
            value = _check_record_identity(_parse_object(raw, label), filename, label)
            existing_normalized = validate(value)
            if not _accept_existing or existing_normalized != normalized:
                raise ConflictError(f"record already exists: {Path(filename).stem}")
            pin = PinnedRecord(access, directory, filename, directory_fd, record_fd, value, raw, readonly, MAX_RECORD_BYTES, mode=mode)
            pin.verify_current()
            yield pin
            pin.verify_current()
        except (NotFoundError, UnsafeStateError, ConflictError):
            raise
        except OSError as exc:
            raise UnsafeStateError(f"cannot publish state record {label}: {exc}") from exc
        finally:
            for fd in (sample_fd, record_fd, temp_fd):
                if fd is not None:
                    os.close(fd)
            if cleanup_temp:
                # No mismatch was observed for this outcome. This direct unlink
                # still has the unavoidable same-UID replacement window.
                try:
                    _remove_temp(directory_fd, temporary)
                except UnsafeStateError:
                    pass

def atomic_create(access: StoreAccess, directory: str, filename: str, value: dict) -> None:
    label = access.home / directory / filename
    with publish_json_exact_pinned(
        access, directory, filename, value,
        validate=lambda candidate: _check_record_identity(candidate, filename, label),
        mode=0o600, _accept_existing=False,
    ):
        pass


def atomic_replace(access: StoreAccess, directory: str, filename: str, value: dict) -> None:
    label = access.home / directory / filename
    with access.directory(directory) as directory_fd:
        temporary = f".zxro-tmp-{secrets.token_hex(16)}"
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=directory_fd)
            os.fchmod(fd, 0o600)
            payload = _encoded(value, label)
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = None
            access.verify_directory(directory, directory_fd)
            os.replace(temporary, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            access.verify_directory(directory, directory_fd)
            os.fsync(directory_fd)
            access.verify_directory(directory, directory_fd)
        except BaseException:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
        try:
            record_fd = os.open(filename, os.O_RDONLY | _NOFOLLOW, dir_fd=directory_fd)
            try:
                _check_record_fd(record_fd, label)
            finally:
                os.close(record_fd)
        except OSError as exc:
            raise UnsafeStateError(f"cannot verify replaced state record {label}: {exc}") from exc


def list_names(access: StoreAccess, directory: str) -> list[str]:
    with access.directory(directory) as directory_fd:
        try:
            entries = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise UnsafeStateError(f"cannot list state directory {access.home / directory}: {exc}") from exc
        access.verify_directory(directory, directory_fd)
    names = []
    for name in entries:
        if name.startswith(".zxro-tmp-"):
            continue
        if not name.endswith(".json"):
            raise UnsafeStateError(f"unexpected state entry: {access.home / directory / name}")
        names.append(name)
    return names


def list_records(access: StoreAccess, directory: str) -> list[dict]:
    return [read_json(access, directory, name) for name in list_names(access, directory)]
