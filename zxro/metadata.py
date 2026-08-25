"""Validation for bounded, namespaced record metadata."""

import json
import re
import unicodedata

from .errors import ValidationError

KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
MAX_DEPTH = 4
MAX_STRING_CHARS = 2048
MAX_METADATA_BYTES = 16 * 1024
RESERVED_NAMESPACES = {"zxro"}


def validate_name(value, label="metadata key"):
    if not isinstance(value, str) or value in {".", ".."} or not KEY_PATTERN.fullmatch(value):
        raise ValidationError(f"invalid {label}: {value!r}")
    return value


def _value(value, depth, *, normalize):
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        if len(normalized) > MAX_STRING_CHARS:
            raise ValidationError(f"metadata string exceeds {MAX_STRING_CHARS} characters")
        if not normalize and normalized != value:
            raise ValidationError("metadata string is not NFC-normalized")
        return normalized
    if type(value) in (bool, int):
        return value
    if isinstance(value, list):
        result = []
        for item in value:
            if not (isinstance(item, str) or type(item) in (bool, int)):
                raise ValidationError("metadata arrays may contain scalar values only")
            result.append(_value(item, depth, normalize=normalize))
        return result
    if isinstance(value, dict):
        if depth > MAX_DEPTH:
            raise ValidationError(f"metadata nesting exceeds depth {MAX_DEPTH}")
        return {validate_name(key): _value(item, depth + 1, normalize=normalize) for key, item in value.items()}
    raise ValidationError("metadata values must be objects, strings, integers, booleans, or scalar arrays")


def validate_namespace(namespace, payload, *, normalize=True):
    validate_name(namespace, "metadata namespace")
    if namespace in RESERVED_NAMESPACES:
        raise ValidationError(f"reserved metadata namespace: {namespace}")
    if not isinstance(payload, dict):
        raise ValidationError("metadata namespace payload must be an object")
    # The namespace payload root counts as depth 1.
    return _value(payload, 1, normalize=normalize)


def validate_metadata(metadata, *, normalize=True):
    if not isinstance(metadata, dict):
        raise ValidationError("metadata must be an object")
    result = {namespace: validate_namespace(namespace, payload, normalize=normalize) for namespace, payload in metadata.items()}
    size = len(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if size > MAX_METADATA_BYTES:
        raise ValidationError(f"metadata exceeds {MAX_METADATA_BYTES} UTF-8 bytes")
    return result
