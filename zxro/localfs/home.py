import os
import stat
from pathlib import Path

from zxro.errors import UnsafeStateError

MANAGED_DIRS = ("watchtowers", "work", "turns")


def resolve_home(cli_home: str | None = None) -> Path:
    raw = cli_home if cli_home is not None else os.environ.get("ZXRO_HOME", "~/.zxro")
    return Path(raw).expanduser().absolute()


def check_owned_mode(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise UnsafeStateError(f"cannot inspect state path {path}: {exc}") from exc
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if stat.S_ISLNK(info.st_mode) or not expected:
        raise UnsafeStateError(f"unsafe state path: {path}")
    if info.st_uid != os.geteuid():
        raise UnsafeStateError(f"state path is not owned by current user: {path}")
    if info.st_mode & 0o022:
        raise UnsafeStateError(f"state path is group/world writable: {path}")


def prepare_home(home: Path) -> None:
    if home.exists() or home.is_symlink():
        check_owned_mode(home, directory=True)
    else:
        try:
            home.mkdir(mode=0o700, parents=True)
        except OSError as exc:
            raise UnsafeStateError(f"cannot create home {home}: {exc}") from exc
        os.chmod(home, 0o700)
    check_owned_mode(home, directory=True)


def ensure_layout(home: Path) -> None:
    check_owned_mode(home, directory=True)
    for name in MANAGED_DIRS:
        path = home / name
        if path.exists() or path.is_symlink():
            check_owned_mode(path, directory=True)
        else:
            path.mkdir(mode=0o700)
            os.chmod(path, 0o700)
