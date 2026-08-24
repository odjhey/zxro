---
name: v0x_cli_multiturn_operator_readiness
description: "Behavioral and manual evidence that the merged CLI can carry an operator-driven multi-turn work item without Pi or Claude adapters."
type: report
tags: [v0.x, validation, cli, operator]
status: draft
generated: "OpenAI GPT-5.4, 2026-08-25"
sources:
  - ref: ../../../tests/test_cli_multiturn.py
    credibility: primary
  - ref: ../../../scripts/cli-multiturn-smoke.sh
    credibility: primary
  - ref: ../surfaces/cli.md
    credibility: primary
created_at: "2026-08-25T08:00:00+08:00"
updated_at: "2026-08-25T08:00:00+08:00"
---

# CLI multi-turn operator readiness

## Recommendation

Pass the merged M0 and M1 CLI to operator evaluation for an operator-driven multi-turn flow. The public CLI was sufficient for creation, four role turns, one failed terminal outcome and recovery turn, payload retrieval, mailbox processing, history, and close. No Pi or Claude adapter took part.

This is not an M7 automation claim. The current CLI does not wake a watchtower or dispatch agents. M2 `inspect` and metadata helpers are also not on `master`. Operators can still complete this evaluation with `work show`, `turn list`, `turn show`, mailbox commands, and `artifact path`.

## Automated evidence

`tests/test_cli_multiturn.py` starts every operation as a separate CLI subprocess against a temporary home. It runs this lifecycle:

```text
coder completed
reviewer failed
reviewer recovery completed with one blocker
coder completed with the fix
tester completed
ack all delivery
handle events out of order
close work
```

The test checks payload references and bytes, bounded event envelopes, all terminal outcomes, idempotent and conflicting settlement retries, restart persistence, unread and pending separation, repeated handling, history, and idempotent close. It uses no `zxro` private Python imports or built-in-provider paths.

Commands run on 2026-08-25:

```sh
python3 -m unittest discover -s tests -p 'test_cli_multiturn.py' -v
python3 -m unittest discover -s tests -v
scripts/cli-multiturn-smoke.sh
```

The smoke script prints its state path and removes that directory on exit. Set `ZXRO_SMOKE_KEEP=1` to retain state for inspection, then remove the printed directory manually.

The focused test passed 1 of 1. The full suite passed 84 of 84 after adding it. The pre-change `master` suite passed 83 of 83, so the new coverage preserves the existing M0 and M1 checks.

## Reproducible terminal run

The manual run used the checkout's public executable. `scripts/cli-multiturn-smoke.sh` is the exact durable simulation. The command sequence below shows its main operations. Generated turn and event IDs replace the shell variables shown below.

```sh
ROOT=/path/to/zxro
ZXRO="$ROOT/bin/zxro"
export ZXRO_HOME="$(mktemp -d /tmp/zxro-cli-readiness.XXXXXX)"

"$ZXRO" watchtower create ops --cwd /tmp/zxro-operator
"$ZXRO" work create release-fix --watchtower ops

T1="$("$ZXRO" turn create --work release-fix --agent manual --session coder-1 --cwd /tmp/coder-1)"
printf 'patch ready\nfiles: 2\n' | "$ZXRO" turn settle "$T1" --source manual --status completed --message 'Patch ready for review.' --stdin
P1="$("$ZXRO" artifact path "artifact:$T1:stdin")"
grep -n 'files: 2' "$P1"

T2="$("$ZXRO" turn create --work release-fix --agent manual --session reviewer-1 --cwd /tmp/reviewer-1)"
printf 'review process exit 17\n' | "$ZXRO" turn settle "$T2" --source manual --status failed --message 'Reviewer exited before a verdict.' --stdin

T3="$("$ZXRO" turn create --work release-fix --agent manual --session reviewer-2 --cwd /tmp/reviewer-2)"
printf 'BLOCKER: reject empty token\n' | "$ZXRO" turn settle "$T3" --source manual --status completed --message 'Review found one blocking validation bug.' --stdin

T4="$("$ZXRO" turn create --work release-fix --agent manual --session coder-2 --cwd /tmp/coder-2)"
printf 'tests: 14 passed\n' | "$ZXRO" turn settle "$T4" --source manual --status completed --message 'Validation fixed; tests pass.' --stdin

"$ZXRO" --json turn list --work release-fix
"$ZXRO" --json inbox unread --watchtower ops
"$ZXRO" turn settle "$T4" --source manual --status completed --message 'Validation fixed; tests pass.'
"$ZXRO" turn settle "$T4" --source manual --status failed --message 'conflicting retry'  # exits 4
"$ZXRO" turn create --work missing --agent manual --session bad --cwd /tmp             # exits 3

"$ZXRO" ack --watchtower ops --through 4
"$ZXRO" --json inbox unread --watchtower ops
"$ZXRO" --json inbox pending --watchtower ops
"$ZXRO" inbox handle EVENT4
"$ZXRO" inbox handle EVENT2
"$ZXRO" inbox handle EVENT2
"$ZXRO" --json inbox pending --watchtower ops

# Handle the remaining event IDs returned by `inbox pending`.
"$ZXRO" work close release-fix
"$ZXRO" work close release-fix
"$ZXRO" --json work show release-fix
"$ZXRO" --json turn list --work release-fix
"$ZXRO" --json inbox pending --watchtower ops
rm -rf "$ZXRO_HOME"
```

## Manual observations

The run used `/tmp/zxro-cli-readiness.jJI555` and removed it at the end. The commands exited 0 except for the two expected failures noted above.

After work creation, `work show` reported `release-fix` as open and owned by `ops`. Direct inspection found one watchtower record and one work record with the same IDs. Files were inspected only to confirm durability. No operation or routing decision used a private path or field.

After the first settlement:

- `turn show` reported turn `ff1448d7-88de-474d-a700-ece4897d3d2a` as settled and completed.
- It returned `artifact:ff1448d7-88de-474d-a700-ece4897d3d2a:stdin` and event `evt-b9d64dfc1dfd44b29ab4328568a14f6c`.
- `inbox unread` returned generation 1 with the summary and artifact reference, but not the payload body.
- The turn and artifact records existed after the settlement process exited. `artifact path` then created and returned a verified `.bin` materialization. `grep -n 'files: 2'` read the expected second line through that public path.

After all four settlements, `turn list --work release-fix` reported three completed outcomes and one failed outcome. `inbox unread` reported generations 1 through 4. The durable home contained four turn records, four artifact records, the materialized payload requested above, four event records, four direct event indexes, and mailbox high-water 4 with read ack 0. Event summaries matched `turn show`; payload text remained behind artifact references.

The identical retry of turn 4 returned success and did not create generation 5. A changed retry exited 4. Creating a turn for a missing work item exited 3 and created no turn.

After `ack --through 4`, `inbox unread` returned an empty list while all four events remained in `inbox pending`. Handling generations 4 and 2 removed only those events. Repeating generation 2's handle returned success and created no second handled item. The mailbox showed ack 4, high-water 4, and two unresolved event IDs. Four handled markers existed only after the remaining events were handled.

After two `work close` calls, `work show` reported `closed`. All four turns and events remained available, and `inbox pending` was empty. The final file inventory still contained the watchtower, work, turns, artifacts, immutable events, event indexes, and handled items. Cleanup removed `/tmp/zxro-cli-readiness.jJI555`.

## Limits and compatibility

- This report proves operator orchestration through the CLI, not automatic M7 wake or dispatch.
- `turn list` is deterministic by turn ID, not lifecycle chronology. Generation order is available from `inbox unread` and `inbox pending` until events are handled. Individual settled timestamps remain in `turn show`.
- The merged CLI has no combined `inspect` command. That M2 convenience is not required to complete the flow, but operators need several bounded read commands.
- The manual run used the built-in local provider and no billable service.
- No CLI behavior changed. The added test uses only the existing public commands, so M0 and M1 compatibility remains unchanged.

## Related

- [Validation index](./README.md)
- [v0.x CLI](../surfaces/cli.md)
- [Implementation plan](../execution/implementation-plan.md)
- [Testing and agent workflow](../engineering/testing-and-agent-workflow.md)
