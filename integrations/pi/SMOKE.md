# Recorded acpx and Pi smoke

Run date: 2026-08-25

Versions:

- acpx 0.13.1, invoked as `npx -y acpx@0.13.1`
- Pi 0.84.3
- zxro head `8ea87a0d74f3bf676ebef44875fa2cd0d7a5cd76` plus the child-process fix in PR #16

The machine already had working Pi credentials. The command used a temporary target, temporary `ZXRO_HOME`, an exact acpx package version, denied tool permissions, and removed the temporary directory afterward.

## Commands

Run from the repository root:

```sh
set -euo pipefail
WT=$PWD/.worktrees/int-pi-agent-settlement
SMOKE=$(mktemp -d /tmp/zxro-int-pi-smoke2.XXXXXX)
TARGET=$SMOKE/target
HOME_DIR=$SMOKE/home
ZXRO=$WT/bin/zxro
mkdir -p "$TARGET/.pi/extensions/zxro" "$HOME_DIR"
cp "$WT/integrations/pi/index.ts" "$WT/integrations/pi/adapter.ts" \
  "$TARGET/.pi/extensions/zxro/"
ZXRO_HOME=$HOME_DIR "$ZXRO" watchtower create smoke-wt --cwd "$TARGET"
ZXRO_HOME=$HOME_DIR "$ZXRO" work create smoke-work --watchtower smoke-wt
PI_TURN=$(ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn create \
  --work smoke-work --agent pi --session acpx-smoke --cwd "$TARGET" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
(
  cd "$TARGET"
  ZXRO_HOME=$HOME_DIR \
  ZXRO_TURN_ID=$PI_TURN \
  ZXRO_EXECUTABLE=$ZXRO \
  npx -y acpx@0.13.1 --timeout 90 --deny-all --format quiet \
    pi exec 'Reply with exactly: smoke complete'
)
MANUAL_TURN=$(ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn create \
  --work smoke-work --agent manual --session manual-smoke --cwd "$TARGET" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
printf '%s' '{"event":"agent_settled","stopReason":"stop"}' |
  ZXRO_HOME=$HOME_DIR "$ZXRO" turn settle "$MANUAL_TURN" \
    --source pi --status completed \
    --message 'Pi agent settled after a completed response.' --stdin
ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn show "$PI_TURN"
ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn show "$MANUAL_TURN"
ZXRO_HOME=$HOME_DIR "$ZXRO" --json inbox unread --watchtower smoke-wt
pi --version
npx -y acpx@0.13.1 --version
rm -rf "$SMOKE"
test ! -e "$SMOKE"
```

## Observed result

The acpx invocation exited 0, printed `smoke complete`, and wrote no stderr output.

Pi settlement:

```text
turn:       52b13960-fee7-4e9c-a8f0-54316a3e31ec
event:      evt-4180e5b3624b4fbcb5aae0bfd6532076
generation: 1
outcome:    completed
source:     pi
artifact:   artifact:52b13960-fee7-4e9c-a8f0-54316a3e31ec:stdin
payload sha256: 945515bfe6e147e2d428b55a93e99f28ccd468ae8a0eb8e82075d9ebaf690486
```

Manual settlement:

```text
turn:       168b899f-806e-4e5e-ac3f-30fa9d3695aa
event:      evt-c48d30011ecb411f917e877818886703
generation: 2
outcome:    completed
source:     pi
artifact:   artifact:168b899f-806e-4e5e-ac3f-30fa9d3695aa:stdin
payload sha256: 945515bfe6e147e2d428b55a93e99f28ccd468ae8a0eb8e82075d9ebaf690486
```

Both turns had the same terminal outcome, source, bounded summary, payload digest, and one stdin artifact reference. Their event IDs and generations differed as expected for distinct turns. Inbox output contained two `turn_settled` events at generations 1 and 2. The cleanup check passed after removing `/tmp/zxro-int-pi-smoke2.W3DWPt`.

## Limits

This smoke covers normal completion through a real acpx/Pi session. Hermetic tests cover Pi failure and cancellation classification, duplicate delivery, early child exit, EPIPE, timeout escalation, timeout races, and signal termination. The smoke used credentials already configured on this machine and does not prove credential setup on another host. Global Pi extensions also loaded, but the disposable project extension path identified this adapter and the resulting zxro source, payload digest, turn ID, and event prove its settlement call.
