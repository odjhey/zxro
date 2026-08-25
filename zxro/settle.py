"""Provider-neutral M1 settlement limits and validation helpers."""

import unicodedata

from .errors import ValidationError
from .ids import safe_string

MAX_STDIN_BYTES = 8 * 1024 * 1024 - 4096


def _normalize_bounded(value: str, label: str) -> str:
    value = unicodedata.normalize("NFC", safe_string(value, label))
    if len(value) > 1000:
        raise ValidationError(f"{label} exceeds 1000 Unicode characters")
    return value


def normalize_summary(value: str) -> str:
    return _normalize_bounded(value, "message")


def normalize_verdict(verdict: str | None, needs: str | None) -> tuple[str | None, str | None]:
    if verdict is not None and verdict not in {"done", "partial", "blocked"}:
        raise ValidationError(f"invalid settlement verdict: {verdict!r}")
    if verdict == "blocked":
        if needs is None:
            raise ValidationError("blocked verdict requires --needs")
        return verdict, _normalize_bounded(needs, "needs")
    if needs is not None:
        raise ValidationError("--needs requires a blocked verdict")
    return verdict, None
