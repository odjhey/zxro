import os
import stat
from pathlib import Path

from zxro.errors import UnsafeStateError

MANAGED_DIRS = ("watchtowers", "work", "turns", "artifacts", "artifact-metadata", "inbox", "inbox-events", "inbox-index", "inbox-handled")


def resolve_home(cli_home: str | None = None) -> Path:
    raw = cli_home if cli_home is not None else os.environ.get("ZXRO_HOME", "~/.zxro")
    return Path(os.path.abspath(os.path.expanduser(raw)))


def check_stat(info, path, *, directory: bool) -> None:
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if stat.S_ISLNK(info.st_mode) or not expected:
        raise UnsafeStateError(f"unsafe state path: {path}")
    if info.st_uid != os.geteuid():
        raise UnsafeStateError(f"state path is not owned by current user: {path}")
    if info.st_mode & 0o022:
        raise UnsafeStateError(f"state path is group/world writable: {path}")


def check_owned_mode(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise UnsafeStateError(f"cannot inspect state path {path}: {exc}") from exc
    check_stat(info, path, directory=directory)


def prepare_home(home: Path) -> None:
    if home.exists() or home.is_symlink():
        check_owned_mode(home, directory=True)
        return
    try:
        home.mkdir(mode=0o700, parents=True)
        os.chmod(home, 0o700)
    except OSError as exc:
        raise UnsafeStateError(f"cannot create home {home}: {exc}") from exc
    check_owned_mode(home, directory=True)
