#!/usr/bin/env python3
"""Settle one zxro turn from a documented Claude Code terminal hook."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unicodedata

MAX_HOOK_BYTES = 8 * 1024 * 1024 - 4096
FAILURE_TYPES = {
    "rate_limit", "overloaded", "authentication_failed", "oauth_org_not_allowed",
    "billing_error", "invalid_request", "model_not_found", "server_error",
    "max_output_tokens", "unknown",
}


class HookError(Exception):
    pass


def text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise HookError(f"{name} must be a non-empty string")
    return value


def classify(payload: object) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise HookError("hook payload must be a JSON object")
    event = text(payload.get("hook_event_name"), "hook_event_name")
    text(payload.get("session_id"), "session_id")
    text(payload.get("cwd"), "cwd")

    if event == "Stop":
        if not isinstance(payload.get("stop_hook_active"), bool):
            raise HookError("Stop.stop_hook_active must be a boolean")
        if not isinstance(payload.get("last_assistant_message"), str):
            raise HookError("Stop.last_assistant_message must be a string")
        background = payload.get("background_tasks")
        crons = payload.get("session_crons")
        if not isinstance(background, list) or not isinstance(crons, list):
            raise HookError("Stop task registry fields are missing or malformed")
        if background or crons:
            raise HookError("Stop is not terminal while background tasks or session crons remain")
        return "completed", "Claude turn completed"

    if event == "StopFailure":
        error = text(payload.get("error"), "StopFailure.error")
        if error not in FAILURE_TYPES:
            raise HookError("StopFailure.error is not documented by this adapter")
        return "failed", f"Claude turn failed: {error}"

    if event == "SessionEnd":
        reason = text(payload.get("reason"), "SessionEnd.reason")
        if reason != "prompt_input_exit":
            raise HookError(f"SessionEnd reason {reason!r} is not a cancellation")
        return "cancelled", "Claude turn cancelled: prompt input exit"

    raise HookError(f"unsupported or nonterminal Claude hook event: {event}")


def read_payload() -> tuple[bytes, object]:
    raw = sys.stdin.buffer.read(MAX_HOOK_BYTES + 1)
    if len(raw) > MAX_HOOK_BYTES:
        raise HookError(f"hook payload exceeds {MAX_HOOK_BYTES} bytes")
    try:
        return raw, json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HookError(f"malformed hook JSON: {exc}") from exc


def metadata() -> tuple[str, str]:
    turn_id = text(os.environ.get("ZXRO_TURN_ID"), "ZXRO_TURN_ID")
    home_value = text(os.environ.get("ZXRO_HOME"), "ZXRO_HOME")
    home = Path(home_value)
    if not home.is_absolute() or not home.is_dir():
        raise HookError("ZXRO_HOME must be an existing absolute directory")
    return turn_id, home_value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retain-payload", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        raw, payload = read_payload()
        turn_id, home = metadata()
        status, message = classify(payload)
        message = unicodedata.normalize("NFC", message)
        executable = os.environ.get("ZXRO_CLI", "zxro")
        command = [executable, "turn", "settle", turn_id, "--source", "claude", "--status", status, "--message", message]
        if args.retain_payload:
            command.append("--stdin")
        result = subprocess.run(
            command, input=raw if args.retain_payload else None, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env={**os.environ, "ZXRO_HOME": home}, timeout=args.timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise HookError(f"zxro failed with status {result.returncode}: {detail}")
        return 0
    except subprocess.TimeoutExpired as exc:
        print(f"zxro Claude hook failed: zxro timed out after {exc.timeout} seconds", file=sys.stderr)
        return 1
    except (HookError, OSError) as exc:
        print(f"zxro Claude hook failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
