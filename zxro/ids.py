import os
import re
import uuid
from .errors import ValidationError

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_NATIVE_SESSION_SOURCE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*\Z")


def validate_id(value: str, label: str = "id") -> str:
    if not isinstance(value, str) or value in (".", "..") or not _ID.fullmatch(value):
        raise ValidationError(f"invalid {label}: {value!r}")
    return value


def validate_event_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"evt-[0-9a-f]{32}", value):
        raise ValidationError(f"invalid event id: {value!r}")
    return value


def validate_turn_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValidationError(f"invalid turn id: {value!r}") from None
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValidationError(f"invalid turn id: {value!r}")
    return str(parsed)


def validate_native_session_source(value: str) -> str:
    if not isinstance(value, str) or len(value) > 64 or not _NATIVE_SESSION_SOURCE.fullmatch(value):
        raise ValidationError(f"invalid native session source: {value!r}")
    return value


def safe_string(value: str | None, label: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValidationError(f"{label} is required")
        return None
    if not isinstance(value, str) or not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValidationError(f"invalid {label}")
    return value


def lexical_absolute(value: str) -> str:
    safe_string(value, "cwd")
    return os.path.abspath(os.path.expanduser(value))
