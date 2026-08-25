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
updated_at: "2026-08-25T08:30:00+08:00"
---

# CLI multi-turn operator readiness

## Recommendation

Recommendation: pass the merged M0 and M1 CLI to operator evaluation for an operator-driven multi-turn flow. The public CLI completed six role turns, including failed and cancelled outcomes followed by recovery turns. It also covered payload retrieval, mailbox processing, history, and close. No Pi or Claude adapter took part.

This report remains `draft` until an independent reviewer accepts the evidence. The recommendation is not a release approval or an M7 automation claim. The current CLI does not wake a watchtower or dispatch agents. M2 `inspect`, `turn env`, and `turn run` are not on `master`. Operators can complete this evaluation with `work show`, `turn list`, `turn show`, mailbox commands, and `artifact path`.

## Automated evidence

`tests/test_cli_multiturn.py` starts every operation as a separate CLI subprocess against a temporary home. It runs this lifecycle:

```text
coder completed
reviewer failed
reviewer recovery completed with one blocker
coder completed with the fix
tester cancelled
tester recovery completed
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

The smoke script prints its state path and removes that directory on exit. `ZXRO_SMOKE_KEEP=1` retains state. `ZXRO_SMOKE_INSPECT=1` prints a durable file inventory plus the work, cancelled-turn, and mailbox records. These inspection records corroborate public output; the script never reads them to make lifecycle decisions.

The focused test passed 1 of 1. The full suite passed 84 of 84. The pre-change `master` suite passed 83 of 83, so the new coverage preserves the existing M0 and M1 checks.

## Reproducible terminal run

`scripts/cli-multiturn-smoke.sh` is the checked-in public-CLI simulation. Run all three modes from the repository root:

```sh
# Default mode proves the flow and removes its generated state.
scripts/cli-multiturn-smoke.sh

# Retained mode permits an independent operator to query and inspect the result.
rm -rf /tmp/zxro-cli-readiness-replay
ZXRO_SMOKE_HOME=/tmp/zxro-cli-readiness-replay \
ZXRO_SMOKE_KEEP=1 \
scripts/cli-multiturn-smoke.sh

bin/zxro --home /tmp/zxro-cli-readiness-replay --json work show release-fix
bin/zxro --home /tmp/zxro-cli-readiness-replay --json turn list --work release-fix
bin/zxro --home /tmp/zxro-cli-readiness-replay --json inbox unread --watchtower ops
bin/zxro --home /tmp/zxro-cli-readiness-replay --json inbox pending --watchtower ops

# Inspection mode correlates public output with durable items without using them as commands.
rm -rf /tmp/zxro-cli-readiness-inspect
ZXRO_SMOKE_HOME=/tmp/zxro-cli-readiness-inspect \
ZXRO_SMOKE_KEEP=1 \
ZXRO_SMOKE_INSPECT=1 \
scripts/cli-multiturn-smoke.sh
rm -rf /tmp/zxro-cli-readiness-replay /tmp/zxro-cli-readiness-inspect
```

The script itself contains the exact create, settle, artifact, retry, ack, handle, history, and close commands. It generates six ordered outcomes:

```text
completed, failed, completed, completed, cancelled, completed
```

It resolves the first payload through `artifact path`, retries the final settlement identically, rejects a changed retry, acknowledges through generation 6, handles generations out of order, repeats one handle, and closes twice.

## Manual observations

Attempt 2 ran default cleanup mode and retained inspection mode. Default mode removed its generated directory and exited 0. Retained mode used `/tmp/zxro-cli-readiness-attempt2`, exited 0, and left state until explicit cleanup.

Public reads against the retained home reported:

- `work show release-fix` returned `closed`;
- `turn list --work release-fix` returned six settled turns with four `completed`, one `failed`, and one `cancelled` outcome;
- `inbox unread --watchtower ops` returned `[]` after ack through generation 6;
- `inbox pending --watchtower ops` returned `[]` after all six events were handled;
- the identical final settlement retry succeeded without generation 7, while the conflicting retry exited 4;
- `artifact path` returned a verified materialization whose second line was `files: 2`.

Inspection mode found one watchtower record, one closed work record, six turn records, six immutable event records, six event indexes, six handled items, one mailbox record, six artifact records, and the one requested `.bin` materialization. The cancelled turn record matched the public turn outcome and summary. The mailbox record matched the empty public unread and pending views. Lifecycle commands used only public CLI output; direct file reads served only as durability checks.

The retained directory was removed with:

```sh
rm -rf /tmp/zxro-cli-readiness-attempt2
```

A subsequent `test ! -e /tmp/zxro-cli-readiness-attempt2` passed.

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
