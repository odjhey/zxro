#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ZXRO=${ZXRO:-"$ROOT/bin/zxro"}
STATE=${ZXRO_SMOKE_HOME:-"$(mktemp -d "${TMPDIR:-/tmp}/zxro-cli-readiness.XXXXXX")"}
KEEP=${ZXRO_SMOKE_KEEP:-0}
INSPECT=${ZXRO_SMOKE_INSPECT:-0}
export ZXRO_HOME="$STATE"

cleanup() {
    if [ "$KEEP" = 1 ]; then
        printf 'kept disposable state: %s\n' "$STATE"
    else
        rm -rf "$STATE"
        printf 'removed disposable state: %s\n' "$STATE"
    fi
}
trap cleanup EXIT HUP INT TERM

json_event_id() {
    python3 -c 'import json,sys; events=json.load(sys.stdin)["data"]; print(next(event["event_id"] for event in events if event["generation"] == int(sys.argv[1])))' "$1"
}

printf 'disposable state: %s\n' "$STATE"
"$ZXRO" watchtower create ops --cwd /tmp/zxro-operator
"$ZXRO" work create release-fix --watchtower ops

T1=$("$ZXRO" turn create --work release-fix --agent manual --session coder-1 --cwd /tmp/coder-1)
printf 'patch ready\nfiles: 2\n' | "$ZXRO" turn settle "$T1" --source manual --status completed --message 'Patch ready for review.' --stdin
P1=$("$ZXRO" artifact path "artifact:$T1:stdin")
grep -n 'files: 2' "$P1"

T2=$("$ZXRO" turn create --work release-fix --agent manual --session reviewer-1 --cwd /tmp/reviewer-1)
printf 'review process exit 17\n' | "$ZXRO" turn settle "$T2" --source manual --status failed --message 'Reviewer exited before a verdict.' --stdin
T3=$("$ZXRO" turn create --work release-fix --agent manual --session reviewer-2 --cwd /tmp/reviewer-2)
printf 'BLOCKER: reject empty token\n' | "$ZXRO" turn settle "$T3" --source manual --status completed --message 'Review found one blocking validation bug.' --stdin
T4=$("$ZXRO" turn create --work release-fix --agent manual --session coder-2 --cwd /tmp/coder-2)
printf 'tests: 14 passed\n' | "$ZXRO" turn settle "$T4" --source manual --status completed --message 'Validation fixed; tests pass.' --stdin
T5=$("$ZXRO" turn create --work release-fix --agent manual --session tester-1 --cwd /tmp/tester-1)
printf 'maintenance window started\n' | "$ZXRO" turn settle "$T5" --source manual --status cancelled --message 'Test run cancelled during environment maintenance.' --stdin
T6=$("$ZXRO" turn create --work release-fix --agent manual --session tester-2 --cwd /tmp/tester-2)
printf 'suite: pass\n' | "$ZXRO" turn settle "$T6" --source manual --status completed --message 'Regression suite passed; ready to close.' --stdin

"$ZXRO" --json turn list --work release-fix
EVENTS=$("$ZXRO" --json inbox unread --watchtower ops)
printf '%s\n' "$EVENTS"
"$ZXRO" turn settle "$T6" --source manual --status completed --message 'Regression suite passed; ready to close.'
if "$ZXRO" turn settle "$T6" --source manual --status failed --message 'conflicting retry'; then
    echo 'conflicting retry unexpectedly succeeded' >&2
    exit 1
else
    test "$?" -eq 4
fi

"$ZXRO" ack --watchtower ops --through 6
test "$("$ZXRO" --json inbox unread --watchtower ops)" = '{"data":[],"schema_version":1}'
EVENT6=$(printf '%s\n' "$EVENTS" | json_event_id 6)
EVENT2=$(printf '%s\n' "$EVENTS" | json_event_id 2)
"$ZXRO" inbox handle "$EVENT6"
"$ZXRO" inbox handle "$EVENT2"
"$ZXRO" inbox handle "$EVENT2"
"$ZXRO" --json inbox pending --watchtower ops

for generation in 1 3 4 5; do
    event=$(printf '%s\n' "$EVENTS" | json_event_id "$generation")
    "$ZXRO" inbox handle "$event"
done
"$ZXRO" work close release-fix
"$ZXRO" work close release-fix
"$ZXRO" --json work show release-fix
"$ZXRO" --json turn list --work release-fix
test "$("$ZXRO" --json inbox pending --watchtower ops)" = '{"data":[],"schema_version":1}'

if [ "$INSPECT" = 1 ]; then
    printf '%s\n' 'durable file inventory:'
    find "$STATE" -maxdepth 2 -type f -print | sort
    printf '%s\n' 'work record:'
    python3 -m json.tool "$STATE/work/release-fix.json"
    printf '%s\n' 'cancelled turn record:'
    python3 -m json.tool "$STATE/turns/$T5.json"
    printf '%s\n' 'mailbox record:'
    python3 -m json.tool "$STATE/inbox/ops.json"
fi

printf 'multi-turn CLI smoke passed\n'
