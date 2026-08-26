"""Opt-in, best-effort structured diagnostics for the public CLI."""

from __future__ import annotations

import datetime as _datetime
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .errors import ValidationError

LOG_SCHEMA_VERSION = 1
LEVELS = ("debug", "info", "warning", "error")
CORE_EVENT_NAMES = frozenset({
    "zxro.cli.invocation.started",
    "zxro.cli.invocation.completed",
    "zxro.cli.command.dispatched",
    "zxro.cli.arguments.invalid",
    "zxro.cli.configuration.invalid",
    "zxro.provider.read.started",
    "zxro.provider.read.completed",
    "zxro.provider.read.failed",
    "zxro.provider.mutation.started",
    "zxro.provider.mutation.completed",
    "zxro.provider.mutation.failed",
    "zxro.state.validation.failed",
    "zxro.lock.wait.completed",
    "zxro.settlement.publication.stage_completed",
    "zxro.settlement.publication.stage_failed",
    "zxro.artifact.verification.completed",
    "zxro.artifact.verification.failed",
    "zxro.logging.sink.failed",
})
_LEVEL_ORDER = {name: index for index, name in enumerate(LEVELS)}
MAX_LOG_FILE_BYTES = 5 * 1024 * 1024
MAX_LOG_BACKUPS = 4
MAX_EVENT_BYTES = 64 * 1024
RETENTION_DAYS = 7
_MAX_VALUE_BYTES = 512
_CORRELATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TOKEN_RE = re.compile(
    r"(?i)\b(?:password|passwd|(?:http)?authorization|auth(?:[_\-.]|\s+)?header|cookie|token|(?:x)?api(?:[_\-.]|\s+)?key|(?:access|refresh)[_-]?token|credential|client[_\-.]?secret|secret)(?:[_\-. ](?:value|hash|header))?\s*[:=]\s*(?:(?:basic|bearer)\s+)?[^\s,;]+|\b(?:bearer|basic|token)\s+[^\s,;]+"
)
_TIMESTAMP_RE = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z)")
_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_:/])/(?:[^\s'\",;\)\]]*)")
_DELIMITED_UNIX_PATH_RE = re.compile(r"(?<=[=:,;(\[{])/(?!/)(?:[^\s'\",;\)\]]*)")
_WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/](?:[^\s'\",;\)\]]*)")
_UNC_PATH_RE = re.compile(r"(?<![A-Za-z0-9_:/])(?:\\\\|//)(?:[^\s'\",;\)\]]+)")
_PATH_KEY_TOKENS = frozenset({"path", "paths", "file", "files", "filename", "filepath", "directory", "directories", "dir", "cwd", "home", "root", "location"})
_CONTENT_KEY_TOKENS = frozenset({"prompt", "prompts", "summary", "summaries", "stdin", "stdout", "stderr", "environment", "env", "session", "sessions", "payload", "payloads", "record", "records", "transcript", "body", "content"})
_CREDENTIAL_KEY_TOKENS = frozenset({"password", "passwords", "passwd", "passphrase", "passphrases", "authorization", "authorizations", "cookie", "cookies", "token", "tokens", "secret", "secrets", "credential", "credentials"})
_SENSITIVE_COMPACT_ROOTS = frozenset({
    "password", "passwords", "passwd", "passphrase", "passphrases", "authorization", "authorizations", "cookie", "cookies",
    "token", "tokens", "secret", "secrets", "credential", "credentials", "accesstoken", "accesstokens",
    "refreshtoken", "refreshtokens", "apikey", "apikeys", "authheader", "authheaders", "clientsecret", "clientsecrets",
    "githubtoken", "openaiapikey", "dbpassword", "csrftoken", "bearertoken", "proxyauthorization", "servercookie",
})
_NATIVE_COMPACT_ROOTS = frozenset({"nativeid", "nativeids", "clientnativeid"})
_SENSITIVE_COMPACT_SUFFIXES = frozenset({"value", "values", "hash", "hashes", "header", "headers"})
_MAX_COMPACT_ROOT_POSITION = 16
_OWNER_XATTR = "com.zxro.home-binding" if sys.platform == "darwin" else "user.zxro.home-binding"


def _utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)


def _timestamp(value: _datetime.datetime | None = None) -> str:
    value = value or _utc_now()
    return value.astimezone(_datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fingerprint(value: str, key: bytes) -> str:
    return "fp_" + hashlib.blake2s(value.encode("utf-8", "replace"), key=key, digest_size=10).hexdigest()


def _home_fingerprint(home: Path) -> str:
    physical = os.path.realpath(str(home))
    return "home_" + hashlib.sha256(physical.encode("utf-8", "replace")).hexdigest()[:20]


def _redact_text(value: str, *, path_like: bool = False) -> str:
    value = _TOKEN_RE.sub("[REDACTED]", value)
    if path_like and value:
        return "[PATH]"
    value = _UNC_PATH_RE.sub("[PATH]", value)
    value = _WINDOWS_PATH_RE.sub("[PATH]", value)
    value = _ABSOLUTE_PATH_RE.sub("[PATH]", value)
    return _DELIMITED_UNIX_PATH_RE.sub("[PATH]", value)


def redact_parser_output(value: str) -> str:
    value = _redact_text(value)
    value = _ABSOLUTE_PATH_RE.sub("[PATH]", value)
    value = re.sub(r"(?m)^(.*unrecognized arguments:).*$", r"\1 [ARGUMENTS REDACTED]", value)
    value = re.sub(r"(?m)^(.*invalid choice:).*$", r"\1 [VALUE REDACTED]", value)
    return value


def _key_tokens(value: str) -> set[str]:
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", separated)
    return {token for token in re.split(r"[^a-zA-Z0-9]+", separated.lower()) if token}


def _is_path_key(value: str) -> bool:
    return bool(_key_tokens(value) & _PATH_KEY_TOKENS)


def _compact_concept(compact: str, roots: frozenset[str], *, allow_prefixes: bool = False) -> bool:
    last_position = min(_MAX_COMPACT_ROOT_POSITION, len(compact)) if allow_prefixes else 0
    for position in range(last_position + 1):
        candidate = compact[position:]
        for root in roots:
            if candidate == root or candidate.startswith(root) and candidate[len(root):] in _SENSITIVE_COMPACT_SUFFIXES:
                return True
    return False


def _is_content_key(tokens: set[str], raw_key: str) -> bool:
    if tokens & _CONTENT_KEY_TOKENS:
        return True
    if "native" in tokens and ("id" in tokens or "ids" in tokens):
        return True
    compact = re.sub(r"[^a-z0-9]", "", raw_key.lower())
    if _compact_concept(compact, _NATIVE_COMPACT_ROOTS, allow_prefixes=True) or any(_compact_concept(token, _NATIVE_COMPACT_ROOTS, allow_prefixes=True) for token in tokens):
        return True
    return "artifact" in tokens and not tokens.intersection({"ref", "refs", "id", "ids", "path", "paths"})


def _is_credential_key(tokens: set[str], raw_key: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", raw_key.lower())
    if _compact_concept(compact, _SENSITIVE_COMPACT_ROOTS, allow_prefixes=True) or any(_compact_concept(token, _SENSITIVE_COMPACT_ROOTS, allow_prefixes=True) for token in tokens):
        return True
    return bool(tokens & _CREDENTIAL_KEY_TOKENS) or ("api" in tokens and ("key" in tokens or "keys" in tokens)) or ("auth" in tokens and ("header" in tokens or "headers" in tokens))


def _bounded(value: Any, *, _path_like: bool = False) -> Any:
    if isinstance(value, os.PathLike):
        return "[PATH]"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "[REDACTED]"
    if isinstance(value, str):
        value = _redact_text(value, path_like=_path_like)
        encoded = value.encode("utf-8", "replace")
        if len(encoded) > _MAX_VALUE_BYTES:
            value = encoded[:_MAX_VALUE_BYTES].decode("utf-8", "ignore") + "…"
        return value
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_bounded(item, _path_like=_path_like) for item in list(value)[:16]]
    if isinstance(value, dict):
        bounded = {}
        for key, item in list(value.items())[:32]:
            raw_key = str(key)
            bounded_key = _redact_text(raw_key)[:64]
            key_tokens = _key_tokens(raw_key)
            if _is_content_key(key_tokens, raw_key):
                continue
            credential_key = _is_credential_key(key_tokens, raw_key)
            child_path_like = _path_like or _is_path_key(raw_key)
            bounded[bounded_key] = "[REDACTED]" if credential_key else _bounded(item, _path_like=child_path_like)
        return bounded
    return "[REDACTED]"


def _stable_error(exc: BaseException) -> str:
    name = type(exc).__name__
    return {
        "ValidationError": "validation_error",
        "NotFoundError": "not_found",
        "ConflictError": "conflict",
        "UnsafeStateError": "unsafe_state",
        "OSError": "os_error",
    }.get(name, "command_error")


def _get_owner_binding(path: Path) -> bytes | None:
    if hasattr(os, "getxattr"):
        try:
            return os.getxattr(path, _OWNER_XATTR)
        except OSError as exc:
            missing = {getattr(errno, "ENODATA", -1), getattr(errno, "ENOATTR", -1)}
            if exc.errno in missing:
                return None
            raise
    result = subprocess.run(
        ["xattr", "-p", _OWNER_XATTR, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.rstrip(b"\n")
    if result.returncode == 1:
        return None
    raise OSError("cannot inspect log binding metadata")


def _set_owner_binding(path: Path, owner: str) -> None:
    value = owner.encode("ascii")
    if hasattr(os, "setxattr"):
        os.setxattr(path, _OWNER_XATTR, value, 0)
        return
    subprocess.run(["xattr", "-w", _OWNER_XATTR, owner, str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _check_owner_mode(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValidationError("cannot inspect log path") from exc
    if stat.S_ISLNK(info.st_mode) or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode)):
        raise ValidationError("unsafe log path")
    expected_mode = 0o700 if directory else 0o600
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != expected_mode:
        raise ValidationError("log path does not have owner-only permissions")


def _validate_log_path(raw: str, home: Path) -> Path:
    if not raw:
        raise ValidationError("log file path must not be empty")
    path = Path(os.path.abspath(os.path.expanduser(raw)))
    try:
        physical_home = Path(os.path.realpath(str(home)))
        physical_path = Path(os.path.realpath(str(path)))
        if path == home or path.is_relative_to(home) or physical_path == physical_home or physical_path.is_relative_to(physical_home):
            raise ValidationError("log file must be outside ZXRO_HOME")
    except ValueError:
        raise ValidationError("invalid log file path") from None
    _check_owner_mode(path.parent, directory=True)
    ancestor = path.parent
    while ancestor != ancestor.parent:
        try:
            if stat.S_ISLNK(ancestor.lstat().st_mode) and ancestor.parent != ancestor.parent.parent:
                raise ValidationError("unsafe log path")
        except OSError as exc:
            raise ValidationError("cannot inspect log path") from exc
        ancestor = ancestor.parent
    if path.exists() or path.is_symlink():
        _check_owner_mode(path, directory=False)
    for index in range(1, MAX_LOG_BACKUPS + 1):
        backup = Path(f"{path}.{index}")
        if backup.exists() or backup.is_symlink():
            _check_owner_mode(backup, directory=False)
    return path


@dataclass(frozen=True)
class LogConfig:
    level: str = "off"
    format: str = "human"
    file: Path | None = None
    correlation_id: str | None = None
    sensitive: bool = False

    @property
    def enabled(self) -> bool:
        return self.level != "off"

    @classmethod
    def from_args(cls, args, home: Path) -> "LogConfig":
        def setting(flag: str, env_name: str, default: str | None = None) -> str | None:
            value = getattr(args, flag)
            if value is not None:
                return value
            value = os.environ.get(env_name)
            return value if value not in (None, "") else default

        level = setting("log_level", "ZXRO_LOG_LEVEL", "off")
        if level not in ("off",) + LEVELS:
            raise ValidationError("invalid log level")
        format_name = setting("log_format", "ZXRO_LOG_FORMAT", "human")
        if format_name not in ("human", "jsonl"):
            raise ValidationError("invalid log format")
        correlation_id = setting("correlation_id", "ZXRO_CORRELATION_ID")
        if correlation_id is not None and not _CORRELATION_RE.fullmatch(correlation_id):
            raise ValidationError("invalid correlation id")
        file_name = setting("log_file", "ZXRO_LOG_FILE")
        file_path = _validate_log_path(file_name, home) if file_name is not None else None
        return cls(level, format_name, file_path, correlation_id, bool(getattr(args, "log_sensitive", False)))


class _FileSink:
    def __init__(self, path: Path, format_name: str, owner: str | None = None):
        self.path = path
        self.format_name = format_name
        self.owner = owner
        self._validate()
        if owner is not None:
            self._with_lock(self._prepare_owner)
        self._with_lock(self._prune)

    def _validate(self) -> None:
        _check_owner_mode(self.path.parent, directory=True)
        for index in range(0, MAX_LOG_BACKUPS + 1):
            path = self.path if index == 0 else Path(f"{self.path}.{index}")
            if path.exists() or path.is_symlink():
                _check_owner_mode(path, directory=False)
    def _prepare_owner(self) -> None:
        if self.owner is None:
            return
        family = (self.path, *(Path(f"{self.path}.{i}") for i in range(1, MAX_LOG_BACKUPS + 1)))
        for path in family:
            if not path.exists():
                continue
            binding = _get_owner_binding(path)
            if binding is not None and binding.decode("ascii", "replace") != self.owner:
                raise OSError("diagnostic log belongs to another home")
            if path.stat().st_size and binding is None:
                raise OSError("diagnostic log has no home binding")
        if self.path.exists() and _get_owner_binding(self.path) is None:
            _set_owner_binding(self.path, self.owner)

    def _with_lock(self, function):
        fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            return function()
        finally:
            os.close(fd)

    @staticmethod
    def _newest_event(path: Path) -> _datetime.datetime | None:
        newest = None
        try:
            with path.open("rb") as stream:
                for raw in stream:
                    try:
                        line = raw.decode("utf-8", "replace")
                        if line.startswith("{"):
                            value = json.loads(line)
                            stamp = value.get("timestamp")
                        else:
                            match = _TIMESTAMP_RE.search(line)
                            stamp = match.group(1) if match else None
                        if stamp:
                            parsed = _datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                            newest = parsed if newest is None or parsed > newest else newest
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue
        except FileNotFoundError:
            return None
        return newest

    def _prune(self) -> None:
        self._validate()
        cutoff = _utc_now() - _datetime.timedelta(days=RETENTION_DAYS)
        for index in range(0, MAX_LOG_BACKUPS + 1):
            path = self.path if index == 0 else Path(f"{self.path}.{index}")
            if not path.exists():
                continue
            newest = self._newest_event(path)
            if newest is not None and newest < cutoff:
                path.unlink()
            elif newest is None and path.stat().st_size == 0:
                path.unlink()

    def _rotate(self) -> None:
        oldest = Path(f"{self.path}.{MAX_LOG_BACKUPS}")
        if oldest.exists():
            oldest.unlink()
        for index in range(MAX_LOG_BACKUPS - 1, 0, -1):
            source = Path(f"{self.path}.{index}")
            if source.exists():
                os.replace(source, Path(f"{self.path}.{index + 1}"))
        if self.path.exists():
            os.replace(self.path, Path(f"{self.path}.1"))

    def append(self, line: bytes) -> None:
        if len(line) > MAX_EVENT_BYTES:
            raise OSError("diagnostic event exceeds the per-event limit")

        def write():
            self._prepare_owner()
            self._prune()
            self._validate()
            try:
                size = self.path.stat().st_size if self.path.exists() else 0
                if size + len(line) > MAX_LOG_FILE_BYTES:
                    self._rotate()
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(self.path, flags, 0o600)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                        raise OSError("unsafe active log file")
                    if self.owner is not None and _get_owner_binding(self.path) is None:
                        _set_owner_binding(self.path, self.owner)
                    view = memoryview(line)
                    while view:
                        written = os.write(fd, view)
                        if written <= 0:
                            raise OSError("diagnostic log write made no progress")
                        view = view[written:]
                finally:
                    os.close(fd)
            except FileNotFoundError as exc:
                raise OSError("log directory disappeared") from exc

        self._with_lock(write)


class _StderrSink:
    def __init__(self, stream: TextIO, format_name: str):
        self.stream = stream
        self.format_name = format_name

    def append(self, line: bytes) -> None:
        buffer = getattr(self.stream, "buffer", None)
        if buffer is not None:
            buffer.write(line)
            buffer.flush()
        else:
            self.stream.write(line.decode("utf-8"))
            self.stream.flush()


class DiagnosticLogger:
    """One invocation's ordered event stream."""

    def __init__(self, config: LogConfig, home: Path, *, stream: TextIO | None = None, clock=None):
        self.config = config
        self.home = home
        self._clock = clock or time.monotonic
        self._started = self._clock()
        self._sequence = 0
        self._key = secrets.token_bytes(16)
        self.invocation_id = "inv-" + secrets.token_hex(10)
        self._sink_failed = False
        self._fallback_written = False
        self._active_resource = None
        if not config.enabled:
            self._sink = None
        elif config.file is not None:
            try:
                self._sink = _FileSink(config.file, config.format, _home_fingerprint(home))
            except Exception as exc:  # diagnostics must not alter command behavior
                self._sink = None
                self._sink_warning(exc)
        else:
            self._sink = _StderrSink(stream or __import__("sys").stderr, config.format)

    @property
    def diagnostics_on_stderr(self) -> bool:
        return self.config.enabled and self.config.file is None

    @property
    def stderr_is_structured(self) -> bool:
        return self.diagnostics_on_stderr and self.config.format == "jsonl"

    def _sink_warning(self, exc: BaseException) -> None:
        # This CLI has one selected sink. There is no remaining diagnostic
        # destination to report through, so fail-open without touching command
        # stdout or stderr.
        return

    def _correlation(self, resource: str | None) -> dict[str, str]:
        result = {"home": _fingerprint(str(Path(os.path.realpath(self.home))), self._key)}
        if self.config.correlation_id:
            result["correlation_id"] = self.config.correlation_id
        if resource:
            result["resource"] = resource if self.config.sensitive else _fingerprint(resource, self._key)
        return result

    def _line(self, event: dict[str, Any]) -> bytes:
        if self.config.format == "jsonl":
            return (json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        attrs = json.dumps(event["attributes"], sort_keys=True, separators=(",", ":"), allow_nan=False)
        correlation = json.dumps(event["correlation"], sort_keys=True, separators=(",", ":"), allow_nan=False)
        duration = f" duration_ms={event['duration_ms']}" if "duration_ms" in event else ""
        line = (
            f"{event['timestamp']} {event['level'].upper()} {event['event_name']} "
            f"schema={event['log_schema_version']} event_version={event['event_version']} process={event['process']} "
            f"sequence={event['sequence']} invocation_id={event['invocation_id']} "
            f"home={event['correlation']['home']} correlation={correlation}{duration} {attrs}\n"
        )
        return line.encode("utf-8")

    def emit(self, event_name: str, level: str = "info", *, attributes: dict[str, Any] | None = None, resource: str | None = None, terminal: bool = False, duration_ms: float | None = None) -> None:
        if not self.config.enabled or level not in _LEVEL_ORDER:
            return
        if not terminal and _LEVEL_ORDER[level] < _LEVEL_ORDER[self.config.level]:
            return
        if self._sink is None:
            return
        try:
            self._sequence += 1
            event: dict[str, Any] = {
                "log_schema_version": LOG_SCHEMA_VERSION,
                "event_name": event_name,
                "event_version": 1,
                "timestamp": _timestamp(),
                "level": level,
                "process": "cli",
                "invocation_id": self.invocation_id,
                "sequence": self._sequence,
                "correlation": self._correlation(resource),
                "attributes": _bounded(attributes or {}),
            }
            if duration_ms is not None:
                event["duration_ms"] = max(0.0, round(float(duration_ms), 3))
            line = self._line(event)
            if len(line) > MAX_EVENT_BYTES:
                raise OSError("diagnostic event exceeds the per-event limit")
            self._sink.append(line)
        except Exception as exc:
            self._sink = None
            self._sink_failed = True
            self._sink_warning(exc)

    def start(self, command: str, resource: str | None = None) -> None:
        self._active_resource = resource
        self.emit("zxro.cli.invocation.started", "info", attributes={"command": command}, resource=resource)
        self.emit("zxro.cli.command.dispatched", "debug", attributes={"command": command}, resource=resource)

    def provider_start(self, command: str, mutation: bool, resource: str | None = None) -> None:
        family = "mutation" if mutation else "read"
        self.emit(f"zxro.provider.{family}.started", "debug", attributes={"command": command}, resource=resource)

    def provider_done(self, command: str, mutation: bool, started: float, error: str | None = None, resource: str | None = None) -> None:
        family = "mutation" if mutation else "read"
        name = f"zxro.provider.{family}.failed" if error else f"zxro.provider.{family}.completed"
        level = "error" if error else "info"
        attrs = {"command": command, ("error_code" if error else "result_code"): error or "success"}
        self.emit(name, level, attributes=attrs, resource=resource, duration_ms=(self._clock() - started) * 1000)
    def lock_wait(self, duration_ms: float) -> None:
        self.emit(
            "zxro.lock.wait.completed",
            "debug",
            attributes={"result_code": "success"},
            resource=self._active_resource,
            duration_ms=duration_ms,
        )

    def settlement_stage(self, stage: str, success: bool, duration_ms: float, exc: BaseException | None = None) -> None:
        failed = not success
        self.emit(
            "zxro.settlement.publication.stage_failed" if failed else "zxro.settlement.publication.stage_completed",
            "error" if failed else "info",
            attributes={"stage": stage, ("error_code" if failed else "result_code"): error_code(exc) if failed else "success"},
            resource=self._active_resource,
            duration_ms=duration_ms,
        )

    def artifact_verification(self, success: bool, duration_ms: float, exc: BaseException | None = None) -> None:
        failed = not success
        self.emit(
            "zxro.artifact.verification.failed" if failed else "zxro.artifact.verification.completed",
            "error" if failed else "info",
            attributes={("error_code" if failed else "result_code"): error_code(exc) if failed else "success"},
            resource=self._active_resource,
            duration_ms=duration_ms,
        )

    def finish(self, exit_code: int, error: str | None = None) -> None:
        attrs: dict[str, Any] = {"process_exit_code": exit_code}
        attrs["error_code" if error else "result_code"] = error or "success"
        self.emit(
            "zxro.cli.invocation.completed",
            "info" if not error else "error",
            attributes=attrs,
            terminal=True,
            duration_ms=(self._clock() - self._started) * 1000,
        )


def error_code(exc: BaseException) -> str:
    return _stable_error(exc)


def validate_correlation(value: str) -> bool:
    return bool(_CORRELATION_RE.fullmatch(value))
