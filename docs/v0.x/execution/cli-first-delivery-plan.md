---
name: v0x_cli_first_delivery_plan
description: "Concrete delivery plan for the CLI-first milestone: three stacked PRs, parallel test and docs tracks, repository layout, locked implementation decisions, and test-to-contract mapping."
type: plan
tags: [v0.x, execution, delivery, cli]
status: draft
generated: "Claude Fable 5, 2026-08-24"
created_at: "2026-08-24T17:06:13+08:00"
updated_at: "2026-08-25T18:48:31+08:00"
---

# CLI-first delivery plan

## Outcome

Deliver the zxro CLI with the built-in file provider only, tested against the [durable store contract](../../architecture/contracts/durable-store.md) and the [v0.x CLI spec](../surfaces/cli.md), with CI green on every merge. This plan concretizes milestones M0 through M2 of the [implementation plan](./implementation-plan.md) into reviewable pull requests. External store adapters and Pi/Claude integrations start only after this stack merges.

Implementers must treat the contract and CLI spec as authoritative. Where this plan fixes a choice the specs left open, the choice is recorded in [locked implementation decisions](#locked-implementation-decisions) so review can challenge it in one place.

## Delivery structure

Three stacked pull requests, each independently reviewable and CI-gated:

```text
master
  └─ PR1  M0: skeleton, provider boundary, watchtower/work/turn CRUD, CI
       └─ PR2  M1: artifacts, turn settle, inbox unread/pending/handle, ack
            └─ PR3  M2: inspect, turn env, turn bind, docs closure
```

Work that may proceed in parallel once PR1 exists:

| Track | Content | Merge point |
|---|---|---|
| A | PR2 implementation: settlement orchestration and mailbox provider | PR2 branch |
| B | Conformance tests for settlement, mailbox, crash gap, and concurrency, written test-first against the provider boundary from PR1 | PR2 branch |
| C | Docs: task cards per PR, [contract conventions](../../architecture/contracts/conventions.md) filled in, [decision 0002](../../decisions/0002-separate-delivery-from-attention.md) promoted from proposed to current, exit codes finalized in the CLI spec | PR3 branch or a parallel docs PR |

Tracks A and B use the PR2 branch as their integration point. Each PR merges only when `python3 -m unittest discover -s tests -v` passes locally and in CI and review is complete.

All git worktree work stays under `./.worktrees/`.

## Repository layout

Introduced in PR1:

```text
bin/zxro                  # exec shim -> python3 -m zxro; runnable from a checkout
zxro/
  __init__.py             # version
  __main__.py
  cli.py                  # argparse tree, handlers, human and --json rendering
  errors.py               # error hierarchy mapped to exit codes
  ids.py                  # identifier and reference validation
  contract.py             # provider protocols and record dataclasses
  settle.py               # settlement orchestration across capabilities (PR2)
  localfs/                # built-in provider; private behind contract.py
    home.py               # $ZXRO_HOME resolution, layout, path and symlink safety
    ioutil.py             # flock, atomic write (tmp + fsync + os.replace), fail-closed indexed JSON
    registry.py  work.py  turn.py  artifact.py  mailbox.py
tests/
  helpers.py              # run_cli() subprocess helper, temporary-home fixture
  test_cli_*.py           # black-box CLI tests via subprocess and temporary $ZXRO_HOME
  conformance/base.py     # provider-neutral semantic suite, parameterized by provider factory
  conformance/test_builtin_provider.py
  test_localfs_invariants.py
  test_concurrency.py  test_crash_gap.py  test_context_cost.py
.github/workflows/ci.yml  # unittest discover on ubuntu and macos, Python 3.11
```

Boundary rule from [testing and agent workflow](../engineering/testing-and-agent-workflow.md): CLI tests exercise commands through `subprocess`; the conformance suite targets the internal provider boundary so the same cases can later run against adapter compositions unchanged. Only `test_localfs_invariants.py` may hard-code built-in file paths.

## Locked implementation decisions

These choices satisfy the contracts but were not fully fixed by them. Challenge them in PR1 review, not later.

### Exit codes

| Code | Class |
|---|---|
| 0 | success |
| 2 | usage or validation error (argparse default) |
| 3 | missing work, turn, event, or artifact |
| 4 | conflict or invariant violation: duplicate ID, conflicting settlement, backwards ack |
| 5 | unsafe or malformed durable state |
| 6 | child-process failure (reserved for the deferred `turn run`) |

Errors go to stderr and leave stdout empty. Successful `--json` output must be one compact version 1 envelope.

### Built-in provider home layout

```text
$ZXRO_HOME/
  watchtowers/<id>.json
  work/<id>.json
  turns/<turn-id>.json            # includes session binding and settlement fields
  artifacts/<turn-id>--<kind>.json            # durable artifact record
  artifacts/<turn-id>--<kind>.bin             # verified local materialization
  inbox/<watchtower-id>.json                  # ack, high-water, unresolved IDs
  inbox-events/<watchtower>--<generation>.json
  inbox-index/<event-id>.json                 # direct event lookup
  inbox-handled/<event-id>.json
  .lock                           # store lock
```

This layout is a provider implementation detail. Tests and callers other than `test_localfs_invariants.py` must not depend on it. M1 uses one bounded record per immutable event and handled marker rather than one ever-growing event-stream record. Per-watchtower high-water and unresolved indexes let `unread` read only generations after ack, let `pending` read only unresolved IDs, and let `handle` use direct event-ID lookup. Handled history and other watchtowers do not add reads to these operations.

### Concurrency

One exclusive `fcntl.flock` on `$ZXRO_HOME/.lock` serializes all mutations. The contract permits safe serialization, and the target load is 10 to 12 near-simultaneous settlements. Every record write uses temp file, `fsync`, then `os.replace`. Immutable mailbox event records are created under the same lock. Finer-grained locking is a later optimization, not a v0.x requirement.

### Settlement

`turn settle` must follow the documented order: persist the `--stdin` payload as an artifact when present, allocate and commit the event ID with terminal turn state, publish one unhandled mailbox event carrying that identity, then report success. Idempotency: a retry with identical outcome and normalized summary returns the existing settlement and republishes a missing event; omitted retry stdin is allowed, supplied bytes must match the first payload, and a payload cannot be added later. A differing outcome, summary, or supplied payload exits 4. Event IDs are `evt-` plus `uuid4().hex`; generation is the previous mailbox generation plus one, assigned under the store lock.

For the required black-box crash-gap test, the CLI honors a test-only environment knob `ZXRO_FAULT_EXIT_AFTER=turn-commit` that exits between terminal commit and event publication. The conformance suite also drives the same gap directly through the provider boundary.

### Identifiers, summaries, timestamps

- Watchtower IDs, work IDs, and artifact kinds must match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` and are rejected before use as path components; `.` and `..` are invalid.
- Turn IDs are UUIDv4. Artifact references are `artifact:<turn-uuid>:<kind>`.
- Summaries are NFC-normalized; content longer than 1,000 Unicode characters is rejected with exit 2.
- Timestamps are local-offset ISO 8601 and are never used for uniqueness or ordering.
- `artifact path` verifies the owned regular-file materialization against the durable byte count and SHA-256 while resolving it beneath the active home, and fails closed on symlinks or changed content.

## PR contents

### PR1 — M0: skeleton and durable CRUD

- Package skeleton, `bin/zxro`, errors, ID validation, provider protocols, `localfs` registry/work/turn.
- Commands: `watchtower create|show|list`, `work create|show|list|close`, `turn create|show|list` with `--native-session-id`, global `--home` and `--json`.
- Tests: per-command black-box cases covering duplicate rejection, unknown-parent rejection, bounded `work show`, list filters, and two-home isolation with identical IDs; localfs invariants for atomic writes, malformed-state fail-closed behavior, and path safety; conformance base with CRUD and isolation cases.
- CI workflow.

### PR2 — M1: settlement and durable mailbox

- `localfs` artifact and mailbox providers, settlement orchestrator.
- Commands: `turn settle` (`--source`, `--status`, `--message`, `--stdin`), `inbox unread`, `inbox pending`, `inbox handle [--watchtower]`, `ack --watchtower --through`, `artifact path`.
- Tests, mapped to the contract conformance profile and the gates in the [Rozoro lessons report](../../reports/2026-08-24-rozoro-lessons.md):
  - the delivery-and-attention fixture from [testing and agent workflow](../engineering/testing-and-agent-workflow.md): publish generations 1 to 3, read, ack through 3, all remain pending, handle out of order, repeat handle is a no-op, close stays independent;
  - the burst gate: settle events 1 to 10, ack through 10, handle only 8 and 3, every other event remains pending while `unread` is empty;
  - idempotent versus conflicting settlement; settling an unknown turn creates no event;
  - crash gap through both the environment knob and the provider boundary: retry produces exactly one event with stable ID and generation, the event begins unhandled, and no event is visible without its terminal turn result;
  - 10 to 12 concurrent settlements: no lost writes, unique ordered generations, stable event IDs;
  - summary bound enforcement; `--stdin` payload becomes an artifact and never enters the event envelope;
  - ack rules: never backwards, never beyond the highest generation, repeat allowed.

### PR3 — M2: operator ergonomics and docs closure

- Commands: `inspect <work-id>` (read-only joined metadata: turns, artifact counts and bytes, highest generation, ack, unread and pending counts), `turn env`, and `turn bind` per the [session binding contract](../../architecture/contracts/session-binding.md) (enrichment only, idempotent repeat, conflicting native ID exits 4).
- The progressive-disclosure fixture: many settled turns with large synthetic artifacts; growing an old artifact must not change `unread`, `pending`, `show`, or `inspect` output.
- Manual full-loop walkthrough from the CLI spec, executed in a disposable home and recorded as validation evidence.
- Track C docs: task cards, conventions, decision 0002 status, exit-code finalization, index maintenance.

## Deferred

External store adapters (Beads, mail CLI), the Pi extension, Claude hooks, `turn run`, watchtower wake, any daemon or socket, and Windows support remain out of scope until this stack merges. Adapters then reuse the same conformance suite as opt-in integration tests, followed by live acpx, Pi, and Claude smoke tests.

## Acceptance criteria

- [ ] Every PR passes `python3 -m unittest discover -s tests -v` locally and in CI.
- [ ] The built-in provider passes the conformance suite from PR2 onward.
- [ ] Concurrency, crash-gap, delivery-and-attention, and context-cost fixtures pass.
- [ ] The manual walkthrough in the [CLI spec](../surfaces/cli.md) succeeds verbatim in a disposable home.
- [ ] Each success criterion in [goal and scope](../scope/goal-and-scope.md) and each conformance profile item in the [durable store contract](../../architecture/contracts/durable-store.md) maps to at least one named test, listed in the final PR description.

## Human gates

- Gate 0 (scope): approval of this plan authorizes implementation of PR1 through PR3.
- Gate 1 (binding choices): the [locked implementation decisions](#locked-implementation-decisions) become binding at PR1 merge.
- Promoting [decision 0002](../../decisions/0002-separate-delivery-from-attention.md) to `current` requires operator sign-off in Track C.

## Related

- [Execution index](./README.md)
- [Implementation plan](./implementation-plan.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [v0.x CLI](../surfaces/cli.md)
- [Testing and agent workflow](../engineering/testing-and-agent-workflow.md)
- [Goal and scope](../scope/goal-and-scope.md)
