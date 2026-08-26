import argparse
import contextlib
import io
import json
import os
import sys
import time
import traceback

from .contract import Artifact
from .diagnostics import DiagnosticLogger, LogConfig, error_code, redact_parser_output
from .errors import NotFoundError, UnsafeStateError, ValidationError, ZxroError
from .ids import validate_event_id, validate_id, validate_turn_id
from .localfs import m1_capabilities, providers, resolve_home
from .localfs.ioutil import observe_lock
from .metadata import validate_namespace
from .settle import MAX_STDIN_BYTES


def parser():
    root = argparse.ArgumentParser(prog="zxro")
    root.add_argument("--home")
    root.add_argument("--json", action="store_true", dest="json_output")
    root.add_argument("--log-level", choices=("off", "error", "warning", "info", "debug"), default=None, help=argparse.SUPPRESS)
    root.add_argument("--log-format", choices=("human", "jsonl"), default=None, help=argparse.SUPPRESS)
    root.add_argument("--log-file", default=None, help=argparse.SUPPRESS)
    root.add_argument("--correlation-id", default=None, help=argparse.SUPPRESS)
    root.add_argument("--log-sensitive", action="store_true", default=False, help=argparse.SUPPRESS)
    commands = root.add_subparsers(dest="command", required=True)

    watchtower = commands.add_parser("watchtower").add_subparsers(dest="action", required=True)
    create = watchtower.add_parser("create"); create.add_argument("id"); create.add_argument("--cwd", required=True); create.add_argument("--agent"); create.add_argument("--session")
    show = watchtower.add_parser("show"); show.add_argument("id")
    watchtower.add_parser("list")

    work = commands.add_parser("work").add_subparsers(dest="action", required=True)
    create = work.add_parser("create"); create.add_argument("id"); create.add_argument("--watchtower", required=True); create.add_argument("--brief-stdin", action="store_true")
    show = work.add_parser("show"); show.add_argument("id")
    listing = work.add_parser("list"); listing.add_argument("--watchtower"); listing.add_argument("--state")
    close = work.add_parser("close"); close.add_argument("id")
    meta = work.add_parser("meta").add_subparsers(dest="meta_action", required=True)
    meta_set = meta.add_parser("set"); meta_set.add_argument("id"); meta_set.add_argument("namespace"); meta_set.add_argument("--stdin", action="store_true", required=True)
    meta_show = meta.add_parser("show"); meta_show.add_argument("id"); meta_show.add_argument("namespace", nargs="?")
    meta_unset = meta.add_parser("unset"); meta_unset.add_argument("id"); meta_unset.add_argument("namespace")
    brief = work.add_parser("brief").add_subparsers(dest="brief_action", required=True)
    brief_set = brief.add_parser("set"); brief_set.add_argument("id"); brief_set.add_argument("--stdin", action="store_true", required=True)
    brief_path = brief.add_parser("path"); brief_path.add_argument("id")

    turn = commands.add_parser("turn").add_subparsers(dest="action", required=True)
    create = turn.add_parser("create"); create.add_argument("--work", required=True); create.add_argument("--agent", required=True); create.add_argument("--session", required=True); create.add_argument("--cwd", required=True); create.add_argument("--native-session-id")
    show = turn.add_parser("show"); show.add_argument("id")
    listing = turn.add_parser("list"); listing.add_argument("--work"); listing.add_argument("--state")
    bind = turn.add_parser("bind"); bind.add_argument("id"); bind.add_argument("--native-session-id", required=True); bind.add_argument("--source", required=True)
    settle = turn.add_parser("settle"); settle.add_argument("id"); settle.add_argument("--source", required=True); settle.add_argument("--status", required=True, choices=("completed", "failed", "cancelled")); settle.add_argument("--message", required=True); settle.add_argument("--verdict", choices=("done", "partial", "blocked")); settle.add_argument("--needs"); settle.add_argument("--stdin", action="store_true")

    inbox = commands.add_parser("inbox").add_subparsers(dest="action", required=True)
    unread = inbox.add_parser("unread"); unread.add_argument("--watchtower", required=True)
    pending = inbox.add_parser("pending"); pending.add_argument("--watchtower", required=True)
    handle = inbox.add_parser("handle"); handle.add_argument("event_id"); handle.add_argument("--watchtower")
    ack = commands.add_parser("ack"); ack.add_argument("--watchtower", required=True); ack.add_argument("--through", required=True, type=int)
    artifact = commands.add_parser("artifact").add_subparsers(dest="action", required=True)
    put = artifact.add_parser("put"); put.add_argument("turn_id"); put.add_argument("--kind", required=True); put.add_argument("--stdin", action="store_true", required=True)
    path = artifact.add_parser("path"); path.add_argument("ref")
    return root


def _bootstrap_parser():
    root = argparse.ArgumentParser(prog="zxro", add_help=False, allow_abbrev=False)
    root.add_argument("--home")
    root.add_argument("--log-level")
    root.add_argument("--log-format")
    root.add_argument("--log-file")
    root.add_argument("--correlation-id")
    root.add_argument("--log-sensitive", action="store_true", default=False)
    return root


def _bootstrap_args(argv):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return _bootstrap_parser().parse_known_args(argv)[0]
    except SystemExit:
        return None


def _fallback_logging_config(bootstrap):
    level = getattr(bootstrap, "log_level", None) or os.environ.get("ZXRO_LOG_LEVEL", "off")
    format_name = getattr(bootstrap, "log_format", None) or os.environ.get("ZXRO_LOG_FORMAT", "human")
    if level not in ("error", "warning", "info", "debug") or format_name not in ("human", "jsonl"):
        return None
    return LogConfig(level, format_name, None, None, False)


def render(value, machine, *, turn_id_only=False, path_only=False, metadata_only=False):
    if machine:
        print(json.dumps({"schema_version": 1, "data": value}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    elif metadata_only:
        print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    elif turn_id_only:
        print(value["id"])
    elif path_only:
        print(value["path"])
    elif isinstance(value, list):
        for item in value:
            printable = dict(item)
            if "metadata" in printable:
                printable["metadata"] = ",".join(sorted(printable["metadata"]))
            print(" ".join(f"{key}={printable[key]}" for key in printable))
    else:
        print("\n".join(f"{key}: {value[key]}" for key in value))


def _command_name(args) -> str:
    if args.command == "ack":
        return "ack"
    if args.command == "work" and args.action in {"meta", "brief"}:
        return f"work.{args.action}.{getattr(args, args.action + '_action')}"
    return f"{args.command}.{args.action}"


def _resource(args) -> str | None:
    try:
        if args.command == "artifact" and args.action == "path":
            Artifact.parse_ref(args.ref)
            return args.ref
        if args.command == "artifact" and args.action == "put":
            return validate_turn_id(args.turn_id)
        if args.command == "inbox" and args.action == "handle":
            return validate_event_id(args.event_id)
        if args.command == "turn" and args.action in {"show", "bind", "settle"}:
            return validate_turn_id(args.id)
        for name in ("id", "work", "watchtower"):
            value = getattr(args, name, None)
            if value:
                return validate_id(value, name)
    except ValidationError:
        return None
    return None


def _is_mutation(args) -> bool:
    if args.command == "ack":
        return True
    if args.command == "work" and args.action == "meta":
        return args.meta_action != "show"
    return (args.command, args.action) in {
        ("watchtower", "create"),
        ("work", "create"),
        ("work", "close"),
        ("work", "brief"),
        ("turn", "create"),
        ("turn", "bind"),
        ("turn", "settle"),
        ("inbox", "pending"),
        ("inbox", "handle"),
        ("artifact", "put"),
        ("artifact", "path"),
    }


def _run_command(args, *, core_factory=providers, m1_factory=m1_capabilities, observer=None):
    home = resolve_home(args.home)
    registry, work, turn = core_factory(home)
    loop = m1_factory(home, registry, turn)
    if observer is not None:
        if hasattr(loop, "diagnostic_observer"):
            loop.diagnostic_observer = observer
        if hasattr(work, "diagnostic_observer"):
            work.diagnostic_observer = observer
    path_only = False
    metadata_only = False
    if args.command == "watchtower":
        if args.action == "create": value = registry.create(args.id, args.cwd, args.agent, args.session)
        elif args.action == "show": value = registry.get(args.id)
        else: value = registry.list()
    elif args.command == "work":
        if args.action == "create":
            payload = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1) if args.brief_stdin else None
            if payload is not None and len(payload) > MAX_STDIN_BYTES:
                raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
            value = work.create(args.id, args.watchtower, payload)
        elif args.action == "show": value = work.get(args.id)
        elif args.action == "close": value = work.close(args.id)
        elif args.action == "list": value = work.list(args.watchtower, args.state)
        elif args.action == "brief":
            if args.brief_action == "set":
                payload = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
                if len(payload) > MAX_STDIN_BYTES:
                    raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
                value = work.set_brief(args.id, payload)
            else:
                value, path_only = work.brief_path(args.id), True
        elif args.meta_action == "set":
            raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
            if len(raw) > MAX_STDIN_BYTES:
                raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
            try:
                payload = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValidationError(f"invalid metadata JSON: {exc}") from exc
            value = work.set_metadata(args.id, args.namespace, payload)
        elif args.meta_action == "unset": value = work.unset_metadata(args.id, args.namespace)
        else:
            if args.namespace is not None:
                validate_namespace(args.namespace, {})
            record = work.get(args.id)
            metadata = record.metadata or {}
            if args.namespace is not None:
                if args.namespace not in metadata:
                    raise NotFoundError(f"metadata namespace not found: {args.namespace}")
                value = metadata[args.namespace]
            else: value = metadata
            metadata_only = True
    elif args.command == "turn":
        if args.action == "create": value = turn.create(args.work, args.agent, args.session, args.cwd, args.native_session_id)
        elif args.action == "show": value = turn.get(args.id)
        elif args.action == "list": value = turn.list(args.work, args.state)
        elif args.action == "bind": value = turn.bind(args.id, args.native_session_id, args.source)
        else:
            payload = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1) if args.stdin else None
            if payload is not None and len(payload) > MAX_STDIN_BYTES:
                raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
            value, _ = loop.settle(args.id, args.source, args.status, args.message, payload, args.verdict, args.needs)
    elif args.command == "inbox":
        if args.action == "unread": value = loop.unread(args.watchtower)
        elif args.action == "pending": value = loop.pending(args.watchtower)
        else: value = loop.handle(args.event_id, args.watchtower)
    elif args.command == "ack": value = loop.ack(args.watchtower, args.through)
    else:
        if args.action == "put":
            payload = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
            if len(payload) > MAX_STDIN_BYTES:
                raise ValidationError(f"stdin payload too large: maximum is {MAX_STDIN_BYTES} bytes")
            value = loop.artifact_put(args.turn_id, args.kind, payload)
        else:
            value, path_only = loop.artifact_path(args.ref), True
    if hasattr(value, "to_dict"): records = value.to_dict()
    elif isinstance(value, list): records = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
    else: records = value
    if args.command == "turn" and args.action == "list":
        records = [{key: item for key, item in record.items() if key != "artifacts"} for record in records]
    elif args.command == "turn" and args.action == "settle":
        records = {key: item for key, item in records.items() if key != "artifacts"}
    elif args.command == "turn" and args.action in {"show", "bind"} and "artifacts" in records:
        records["artifacts"] = [
            {key: item for key, item in artifact.items() if key in {"ref", "kind", "bytes"}}
            for artifact in records["artifacts"]
        ]
    elif args.command == "artifact" and args.action == "put":
        records = {key: item for key, item in records.items() if key in {"ref", "kind", "bytes"}}
    render(records, args.json_output, turn_id_only=args.command == "turn" and args.action == "create", path_only=path_only, metadata_only=metadata_only)


def run(args, *, core_factory=providers, m1_factory=m1_capabilities, logger=None):
    command = _command_name(args)
    resource = _resource(args)
    mutation = _is_mutation(args)
    if logger is not None:
        logger.start(command, resource)
        logger.provider_start(command, mutation, resource)
    started = logger._clock() if logger is not None else time.monotonic()
    try:
        with observe_lock(logger.lock_wait if logger is not None else None, logger._clock if logger is not None else None):
            _run_command(args, core_factory=core_factory, m1_factory=m1_factory, observer=logger)
    except Exception as exc:
        if logger is not None:
            code = error_code(exc)
            logger.provider_done(command, mutation, started, code, resource)
            if isinstance(exc, UnsafeStateError):
                logger.emit(
                    "zxro.state.validation.failed",
                    "error",
                    attributes={"stage": command, "error_code": code},
                    resource=resource,
                    duration_ms=(logger._clock() - started) * 1000,
                )
        raise
    else:
        if logger is not None:
            logger.provider_done(command, mutation, started, resource=resource)


def _system_exit_code(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if type(value) is int:
        return value & 0xFF
    return 1


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    bootstrap = _bootstrap_args(raw_argv)
    home = resolve_home(getattr(bootstrap, "home", None))
    logger = None
    config_error = None
    if bootstrap is not None:
        try:
            logger = DiagnosticLogger(LogConfig.from_args(bootstrap, home), home)
        except ZxroError as exc:
            config_error = exc
            fallback = _fallback_logging_config(bootstrap)
            if fallback is not None:
                logger = DiagnosticLogger(fallback, home)

    exit_code = 0
    failure_code = None
    try:
        parser_output = io.StringIO()
        parse_context = contextlib.redirect_stderr(parser_output) if logger is not None and logger.config.enabled else contextlib.nullcontext()
        try:
            with parse_context:
                args = parser().parse_args(raw_argv)
        except SystemExit as exc:
            if logger is None or not logger.config.enabled:
                if parser_output.getvalue():
                    sys.stderr.write(parser_output.getvalue())
                raise
            exit_code = _system_exit_code(exc.code)
            failure_code = None if exit_code == 0 else "argparse_error"
            if logger is not None:
                logger.start("parse")
                if exit_code != 0 and logger.config.enabled:
                    logger.emit(
                        "zxro.cli.arguments.invalid",
                        "error",
                        attributes={"error_code": "argparse_error", "diagnostic": redact_parser_output(parser_output.getvalue())},
                        duration_ms=0,
                    )
            if logger is None or not logger.config.enabled or logger.config.file is not None:
                if parser_output.getvalue():
                    sys.stderr.write(parser_output.getvalue())
            return exit_code
        if config_error is not None:
            exit_code = config_error.exit_code
            failure_code = error_code(config_error)
            if logger is not None:
                logger.start("config")
                logger.emit(
                    "zxro.cli.configuration.invalid",
                    "error",
                    attributes={"error_code": failure_code},
                    duration_ms=0,
                )
            if logger is None or not logger.config.enabled:
                print(f"zxro: {config_error}", file=sys.stderr)
            return exit_code
        run(args, logger=logger)
    except ZxroError as exc:
        exit_code = exc.exit_code
        failure_code = error_code(exc)
        if logger is None or not logger.config.enabled or logger.config.file is not None:
            print(f"zxro: {exc}", file=sys.stderr)
    except OSError as exc:
        exit_code = 5
        failure_code = error_code(exc)
        if logger is None or not logger.config.enabled or logger.config.file is not None:
            print(f"zxro: unsafe durable state: {exc}", file=sys.stderr)
    except SystemExit as exc:
        if logger is None or not logger.config.enabled:
            raise
        exit_code = _system_exit_code(exc.code)
        failure_code = None if exit_code == 0 else "system_exit"
    except KeyboardInterrupt:
        if logger is None or not logger.config.enabled:
            raise
        exit_code = 130
        failure_code = "interrupted"
        if logger.config.file is not None:
            traceback.print_exc()
    except Exception:
        if logger is None or not logger.config.enabled:
            raise
        exit_code = 1
        failure_code = "internal_error"
        if logger.config.file is not None:
            traceback.print_exc()
    finally:
        if logger is not None:
            logger.finish(exit_code, failure_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
