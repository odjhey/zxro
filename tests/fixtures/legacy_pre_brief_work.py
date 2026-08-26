# Verbatim snapshot of LocalWorkStore._decode from commit
# 4249e75c5436ce5f6b8b219a431de9df8a4af42e (zxro/localfs/work.py), the last
# revision before the "brief" field was added to the Work durable schema.
# validate_id, validate_metadata, UnsafeStateError, and Work are unchanged
# between that commit and HEAD, so this reuses the real production modules.
from zxro.contract import Work
from zxro.errors import UnsafeStateError
from zxro.ids import validate_id
from zxro.metadata import validate_metadata


def decode_legacy_work_record(data):
    if not {"id", "watchtower_id", "state"} <= set(data) or set(data) - {"id", "watchtower_id", "state", "metadata"} or not all(isinstance(data.get(key), str) for key in ("id", "watchtower_id", "state")) or data.get("state") not in ("open", "closed") or data.get("metadata", {}) is None:
        raise UnsafeStateError("invalid work record schema")
    try:
        validate_id(data["id"], "work id")
        validate_id(data["watchtower_id"], "watchtower id")
        metadata = validate_metadata(data.get("metadata", {}), normalize=False)
    except Exception as exc:
        raise UnsafeStateError(f"invalid work record: {exc}") from exc
    return Work(data["id"], data["watchtower_id"], data["state"], metadata or None)
