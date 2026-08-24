"""Provider-neutral M1 settlement limits and validation helpers."""

import unicodedata

from .errors import ValidationError
from .ids import safe_string

MAX_STDIN_BYTES = 8 * 1024 * 1024 - 4096


def normalize_summary(value: str) -> str:
    value = unicodedata.normalize("NFC", safe_string(value, "message"))
    if len(value) > 1000:
        raise ValidationError("message exceeds 1000 Unicode characters")
    return value
