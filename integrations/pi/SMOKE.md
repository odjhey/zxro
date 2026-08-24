# Recorded acpx and Pi smoke

Run date: 2026-08-25

This run used acpx 0.13.1, Pi 0.84.3, and PR #16 code head `73791acf6309b9d52883fedb0c46b3d121a76533`. The machine already had working Pi credentials.

## Commands

These commands run from any normal checkout of PR #16. They do not depend on a named worktree. The first checks ensure the checkout is the current PR head and the installed tools have the tested versions.

```sh
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
git fetch -q origin pull/16/head
test "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)"
test "$(pi --version)" = 0.84.3
test "$(npx -y acpx@0.13.1 --version)" = 0.13.1

SMOKE=$(mktemp -d /tmp/zxro-int-pi-smoke3.XXXXXX)
TARGET=$SMOKE/target
HOME_DIR=$SMOKE/home
ZXRO=$ROOT/bin/zxro
mkdir -p "$TARGET/.pi/extensions/zxro" "$HOME_DIR"
cp integrations/pi/{index.ts,adapter.ts} "$TARGET/.pi/extensions/zxro/"
grep -Fq 'pi.on("agent_settled"' "$TARGET/.pi/extensions/zxro/index.ts"

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
    pi exec 'Reply with exactly: smoke complete' \
    >"$SMOKE/acpx.out" 2>"$SMOKE/acpx.err"
)
test ! -s "$SMOKE/acpx.err"
grep -Fq 'smoke complete' "$SMOKE/acpx.out"

MANUAL_TURN=$(ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn create \
  --work smoke-work --agent manual --session manual-smoke --cwd "$TARGET" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
printf '%s' '{"event":"agent_settled","stopReason":"stop"}' |
  ZXRO_HOME=$HOME_DIR "$ZXRO" turn settle "$MANUAL_TURN" \
    --source pi --status completed \
    --message 'Pi agent settled after a completed response.' --stdin

PI_JSON=$(ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn show "$PI_TURN")
MANUAL_JSON=$(ZXRO_HOME=$HOME_DIR "$ZXRO" --json turn show "$MANUAL_TURN")
INBOX=$(ZXRO_HOME=$HOME_DIR "$ZXRO" --json inbox unread --watchtower smoke-wt)
printf '%s\n%s\n%s\n' "$PI_JSON" "$MANUAL_JSON" "$INBOX"
ARTIFACT=$(printf '%s' "$PI_JSON" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["artifact_refs"][0])')
ARTIFACT_PATH=$(ZXRO_HOME=$HOME_DIR "$ZXRO" artifact path "$ARTIFACT")
test "$(cat "$ARTIFACT_PATH")" = \
  '{"event":"agent_settled","stopReason":"stop"}'

rm -rf "$SMOKE"
test ! -e "$SMOKE"
```

The copied project extension was the only file in the disposable project's `.pi/extensions` directory. The exact `agent_settled` registration check ran before acpx. After acpx returned, the zxro turn had source `pi` and its stdin artifact contained the adapter's exact semantic payload. Those checks prove project extension discovery even though the pi-acp startup banner listed only global extensions.

## Observed result

The head and version assertions passed. acpx exited 0, printed `smoke complete`, and wrote zero stderr bytes.

Pi settlement:

```text
turn:       3c32198a-5fb5-4551-b4da-c03aa171aa19
event:      evt-5e963b0be2f745b68e68df80d60834f0
generation: 1
outcome:    completed
source:     pi
artifact:   artifact:3c32198a-5fb5-4551-b4da-c03aa171aa19:stdin
payload sha256: 945515bfe6e147e2d428b55a93e99f28ccd468ae8a0eb8e82075d9ebaf690486
```

Manual settlement:

```text
turn:       365db3d4-7356-4155-9a7d-cde5bd83c52b
event:      evt-9c698a49257c4e9ba605c3ce2b7db8dd
generation: 2
outcome:    completed
source:     pi
artifact:   artifact:365db3d4-7356-4155-9a7d-cde5bd83c52b:stdin
payload sha256: 945515bfe6e147e2d428b55a93e99f28ccd468ae8a0eb8e82075d9ebaf690486
```

Both turns had the same outcome, source, bounded summary, payload digest, and artifact shape. Their event IDs and generations differed because they were separate turns. Artifact resolution returned `{"event":"agent_settled","stopReason":"stop"}`. The command removed `/tmp/zxro-int-pi-smoke3.iEVfNR`, and the final absence check passed.

## Limits

This smoke covers normal completion. Hermetic tests cover failure and cancellation classification, duplicate delivery, UUID v4 validation, early exit, EPIPE, bounded stderr, TERM and KILL timeout outcomes, clean-exit timeout races, stress, signals, and POSIX descendant cleanup. Windows does not have the POSIX process-group cleanup check. Credentials were already configured, so this run does not test credential setup. `npx` may need network access if acpx 0.13.1 is not cached.
