import argparse
import json
import sys

from .errors import NotFoundError, ValidationError, ZxroError
from .localfs import m1_capabilities, providers, resolve_home
from .metadata import validate_namespace
from .settle import MAX_STDIN_BYTES


def parser():
    root = argparse.ArgumentParser(prog="zxro")
    root.add_argument("--home")
    root.add_argument("--json", action="store_true", dest="json_output")
    commands = root.add_subparsers(dest="command", required=True)

    watchtower = commands.add_parser("watchtower").add_subparsers(dest="action", required=True)
    create = watchtower.add_parser("create"); create.add_argument("id"); create.add_argument("--cwd", required=True); create.add_argument("--agent"); create.add_argument("--session")
    show = watchtower.add_parser("show"); show.add_argument("id")
    watchtower.add_parser("list")

    work = commands.add_parser("work").add_subparsers(dest="action", required=True)
    create = work.add_parser("create"); create.add_argument("id"); create.add_argument("--watchtower", required=True)
    show = work.add_parser("show"); show.add_argument("id")
    listing = work.add_parser("list"); listing.add_argument("--watchtower"); listing.add_argument("--state")
    close = work.add_parser("close"); close.add_argument("id")
    meta = work.add_parser("meta").add_subparsers(dest="meta_action", required=True)
    meta_set = meta.add_parser("set"); meta_set.add_argument("id"); meta_set.add_argument("namespace"); meta_set.add_argument("--stdin", action="store_true", required=True)
    meta_show = meta.add_parser("show"); meta_show.add_argument("id"); meta_show.add_argument("namespace", nargs="?")
    meta_unset = meta.add_parser("unset"); meta_unset.add_argument("id"); meta_unset.add_argument("namespace")

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


def run(args, *, core_factory=providers, m1_factory=m1_capabilities):
    home = resolve_home(args.home)
    registry, work, turn = core_factory(home)
    loop = m1_factory(home, registry, turn)
    path_only = False
    metadata_only = False
    if args.command == "watchtower":
        if args.action == "create": value = registry.create(args.id, args.cwd, args.agent, args.session)
        elif args.action == "show": value = registry.get(args.id)
        else: value = registry.list()
    elif args.command == "work":
        if args.action == "create": value = work.create(args.id, args.watchtower)
        elif args.action == "show": value = work.get(args.id)
        elif args.action == "close": value = work.close(args.id)
        elif args.action == "list": value = work.list(args.watchtower, args.state)
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


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run(args)
        return 0
    except ZxroError as exc:
        print(f"zxro: {exc}", file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(f"zxro: unsafe durable state: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
