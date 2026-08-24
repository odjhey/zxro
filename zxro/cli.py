import argparse
import json
import sys

from .errors import ZxroError
from .localfs import providers, resolve_home


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

    turn = commands.add_parser("turn").add_subparsers(dest="action", required=True)
    create = turn.add_parser("create"); create.add_argument("--work", required=True); create.add_argument("--agent", required=True); create.add_argument("--session", required=True); create.add_argument("--cwd", required=True); create.add_argument("--native-session-id")
    show = turn.add_parser("show"); show.add_argument("id")
    listing = turn.add_parser("list"); listing.add_argument("--work"); listing.add_argument("--state")
    return root


def render(value, machine, *, turn_id_only=False):
    if machine:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    elif turn_id_only:
        print(value["id"])
    elif isinstance(value, list):
        for item in value:
            print(" ".join(f"{key}={item[key]}" for key in item))
    else:
        print("\n".join(f"{key}: {value[key]}" for key in value))


def run(args):
    registry, work, turn = providers(resolve_home(args.home))
    if args.command == "watchtower":
        if args.action == "create": value = registry.create(args.id, args.cwd, args.agent, args.session)
        elif args.action == "show": value = registry.get(args.id)
        else: value = registry.list()
    elif args.command == "work":
        if args.action == "create": value = work.create(args.id, args.watchtower)
        elif args.action == "show": value = work.get(args.id)
        elif args.action == "close": value = work.close(args.id)
        else: value = work.list(args.watchtower, args.state)
    else:
        if args.action == "create": value = turn.create(args.work, args.agent, args.session, args.cwd, args.native_session_id)
        elif args.action == "show": value = turn.get(args.id)
        else: value = turn.list(args.work, args.state)
    records = [item.to_dict() for item in value] if isinstance(value, list) else value.to_dict()
    render(records, args.json_output, turn_id_only=args.command == "turn" and args.action == "create")


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
