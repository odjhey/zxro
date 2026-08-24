import fcntl
import json
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

from zxro.errors import ConflictError, NotFoundError, UnsafeStateError
from .home import MANAGED_DIRS, check_stat, prepare_home

_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
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
        except FileNotFoundError:
            raise NotFoundError("zxro home does not exist") from None
        except OSError as exc:
            raise UnsafeStateError(f"cannot open zxro home {self.home}: {exc}") from exc

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
        try:
            before = os.stat(name, dir_fd=self.home_fd, follow_symlinks=False)
            check_stat(before, self.home / name, directory=True)
            fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=self.home_fd)
            current = os.fstat(fd)
            check_stat(current, self.home / name, directory=True)
            if not _same_inode(before, current):
                raise UnsafeStateError(f"managed directory changed while opening: {self.home / name}")
        except FileNotFoundError:
            raise NotFoundError(f"managed directory does not exist: {name}") from None
        except OSError as exc:
            raise UnsafeStateError(f"cannot open managed directory {self.home / name}: {exc}") from exc
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


def _record_stat(fd, directory_fd, filename, label):
    try:
        path_stat = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        fd_stat = os.fstat(fd)
    except OSError as exc:
        raise UnsafeStateError(f"cannot verify state record {label}: {exc}") from exc
    check_stat(path_stat, label, directory=False)
    check_stat(fd_stat, label, directory=False)
    if not _same_inode(path_stat, fd_stat):
        raise UnsafeStateError(f"state record changed during operation: {label}")


def read_json(access: StoreAccess, directory: str, filename: str) -> dict:
    label = access.home / directory / filename
    with access.directory(directory) as directory_fd:
        try:
            fd = os.open(filename, os.O_RDONLY | _NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            raise NotFoundError(f"record not found: {Path(filename).stem}") from None
        except OSError as exc:
            raise UnsafeStateError(f"cannot open state record {label}: {exc}") from exc
        try:
            _record_stat(fd, directory_fd, filename, label)
            try:
                chunks = []
                size = 0
                while True:
                    chunk = os.read(fd, min(64 * 1024, MAX_RECORD_BYTES + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_RECORD_BYTES:
                        raise UnsafeStateError(f"state record is too large: {label}")
                value = json.loads(b"".join(chunks).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise UnsafeStateError(f"malformed state record {label}: {exc}") from exc
            _record_stat(fd, directory_fd, filename, label)
            access.verify_directory(directory, directory_fd)
        finally:
            os.close(fd)
    if not isinstance(value, dict):
        raise UnsafeStateError(f"state record is not an object: {label}")
    if filename.endswith(".json") and isinstance(value.get("id"), str) and value["id"] != Path(filename).stem:
        raise UnsafeStateError(f"record identity does not match its path: {label}")
    return value


def atomic_create(access: StoreAccess, directory: str, filename: str, value: dict, *, mode: int = 0o600) -> None:
    label = access.home / directory / filename
    with access.directory(directory) as directory_fd:
        temporary = f".zxro-tmp-{secrets.token_hex(16)}"
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=directory_fd)
            payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            if len(payload) > MAX_RECORD_BYTES:
                raise UnsafeStateError(f"state record is too large: {label}")
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.fchmod(fd, mode)
            os.fsync(fd)
            os.close(fd)
            fd = None
            access.verify_directory(directory, directory_fd)
            try:
                os.link(temporary, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                raise ConflictError(f"record already exists: {Path(filename).stem}") from None
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
            access.verify_directory(directory, directory_fd)
            record_fd = os.open(filename, os.O_RDONLY | _NOFOLLOW, dir_fd=directory_fd)
            try:
                _record_stat(record_fd, directory_fd, filename, label)
            finally:
                os.close(record_fd)
        except BaseException:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise


def atomic_replace(access: StoreAccess, directory: str, filename: str, value: dict, *, mode: int = 0o600) -> None:
    label = access.home / directory / filename
    with access.directory(directory) as directory_fd:
        temporary = f".zxro-tmp-{secrets.token_hex(16)}"
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=directory_fd)
            os.fchmod(fd, 0o600)
            payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            if len(payload) > MAX_RECORD_BYTES:
                raise UnsafeStateError(f"state record is too large: {label}")
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
            os.fchmod(fd, mode)
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
                _record_stat(record_fd, directory_fd, filename, label)
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
