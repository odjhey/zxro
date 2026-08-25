---
name: m7_provider_free_simulation
description: "Run and inspect the deterministic local M7 orchestration simulation without agent providers or credentials."
type: guide
tags: [m7, simulation, operations, testing]
status: current
generated: "OpenAI GPT-5.4, 2026-08-25"
sources:
  - ref: ../../tools/m7_simulation.py
    credibility: primary
  - ref: ../../tests/test_m7_simulation.py
    credibility: primary
  - ref: ../v0.x/execution/implementation-plan.md
    credibility: primary
created_at: "2026-08-25T11:45:00+08:00"
updated_at: "2026-08-25T11:45:00+08:00"
---

# Provider-free M7 simulation

## Purpose

This runbook exercises automatic multi-turn orchestration with the public zxro CLI. It uses a temporary `$ZXRO_HOME`, two temporary target repositories, a separate temporary watchtower project, and short-lived local fake-runtime processes.

The simulation does not start Pi, Claude, acpx, a network provider, or a daemon. It does not read credentials. It is a local behavioral check, not live-provider M7 acceptance.

## Run it

From the repository root:

```sh
bin/zxro-m7-sim --evidence /tmp/zxro-m7-evidence.json
```

The command exits non-zero on a failed assertion. On success, it writes a JSON evidence file and prints its path. The temporary home, repositories, fake runtime script, and child processes are removed before the command exits.

To print the complete report instead of saving it:

```sh
python3 tools/m7_simulation.py
```

## What it exercises

The simulator creates one watchtower and one work item, then runs this bounded sequence:

```text
fake coder-a    -> repo-a
fake reviewer-a -> repo-a
fake coder-b    -> repo-b
fake tester-b   -> repo-b
```

Each stage starts a turn through `bin/zxro`, runs a local fake runtime with `ZXRO_*` metadata, settles through `turn settle --stdin`, and retries the identical settlement. The watchtower side uses `inbox unread`, `ack`, `inbox pending`, and `inbox handle` only.

The first settlement loses both wake notifications and is recovered by a reconciliation poll. Later settlements deliver duplicate wake notifications. The first reconciliation handles the event; the second is a no-op. The simulation then closes the work item twice, retries the terminal settlement after close, and verifies that a new turn is rejected.

The report records:

- the separate watchtower, `repo-a`, and `repo-b` cwd roles;
- four settled turns and generations 1 through 4;
- fake-runtime evidence written inside each target repository;
- one artifact and one handled event per turn;
- empty unread and pending views after close;
- idempotent settlement and close results;
- bounded turn count and cleanup status;
- a snapshot of the JSON records in the temporary durable home.

The durable snapshot is evidence for inspection. It is not a second command interface.

## Inspect the evidence

```sh
python3 - <<'PY' /tmp/zxro-m7-evidence.json
import json
import sys

report = json.load(open(sys.argv[1]))
print(report["result"])
print(report["stop_conditions"])
print(report["cleanup"])
for record in report["durable_evidence"]:
    if record["path"].startswith("inbox-events/"):
        event = record["json"]
        print(event["generation"], event["work_id"], event["outcome"])
PY
```

Expected high-level results are `passed`, four turns, a closed work item, no pending attention, and both cleanup checks set to `true`.

## What this proves

- Public CLI settlement, mailbox delivery, acknowledgement, handling, and close operations can support a deterministic automatic multi-turn loop.
- Dropped wake notifications are recoverable because durable settlement is reconciled from the mailbox.
- Duplicate wake or reconciliation calls do not allocate duplicate turns or events.
- Terminal settlement retries preserve one event per turn.
- Work closure is separate from terminal settlement retry and prevents new turns.
- Target cwd values remain separate from the watchtower cwd.
- The local provider leaves inspectable durable records without requiring an external service.

## What remains blocked

This simulation does not prove:

- Pi or Claude native lifecycle hooks;
- acpx session transport or exact resume;
- live provider authentication, network behavior, quotas, or billing;
- provider adapter conformance;
- a resident watchtower, scheduler, or production wake transport.

Do not report this result as live-provider M7 completion. Live M7 remains blocked on the Pi or Claude integration path and its real harness smoke test.

## Related

- [Playbooks index](./README.md)
- [CLI multi-turn operator readiness](../v0.x/validation/cli-multiturn-operator-readiness.md)
- [Implementation plan](../v0.x/execution/implementation-plan.md)
- [Testing and agent workflow](../v0.x/engineering/testing-and-agent-workflow.md)
- [Product architecture](../architecture/product-architecture.md)
