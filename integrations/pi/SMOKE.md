# Recorded acpx and Pi smoke

Run date: 2026-08-25

The immutable recorded run below tested code commit `73791acf6309b9d52883fedb0c46b3d121a76533` with acpx 0.13.1 and Pi 0.84.3. This file was committed later, so that code commit is not the commit containing this report. The report makes no exact-containing-head claim. The canonical task handoff records later exact-head reruns outside Git, where recording a result cannot change the tested commit. The machine already had working Pi credentials.

## Commands

These commands run from any normal checkout of PR #16. They do not depend on a named worktree. At runtime, the first checks require the checkout to equal the current PR head and require the tested tool versions. They do not claim that the historical output below came from the commit containing this file.

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
cmp integrations/pi/index.ts "$TARGET/.pi/extensions/zxro/index.ts"
cmp integrations/pi/adapter.ts "$TARGET/.pi/extensions/zxro/adapter.ts"
test "$(find "$TARGET/.pi/extensions" -type f | wc -l | tr -d ' ')" = 2
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

The two copied files were byte-for-byte equal to the checkout and were the only files in the disposable project's `.pi/extensions` directory. The exact `agent_settled` registration check ran before acpx. After acpx returned, the inherited turn changed from running to settled with source `pi`, and its artifact resolved to the adapter's exact semantic payload. No global extension emits that zxro source, summary, and payload combination. These checks prove that Pi discovered and ran the project extension even though the pi-acp startup banner listed only global extensions.

## Observed result

For the recorded code commit named above, the version assertions passed. acpx exited 0, printed `smoke complete`, and wrote zero stderr bytes.

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

This smoke covers normal completion. Hermetic tests cover failure and cancellation classification, duplicate delivery, UUID v4 validation, early exit, EPIPE, bounded stderr, TERM and KILL timeout outcomes, clean-exit timeout races, stress, signals, and POSIX descendant cleanup. The adapter rejects Windows before spawning zxro because reliable descendant cleanup requires POSIX process groups. CI runs the integration suite on Linux and macOS. Credentials were already configured, so this run does not test credential setup. `npx` may need network access if acpx 0.13.1 is not cached.
