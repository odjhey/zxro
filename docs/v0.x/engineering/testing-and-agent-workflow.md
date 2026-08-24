---
name: v0x_testing_and_agent_workflow
description: "Dependency-free v0.x test strategy centered on black-box CLI behavior, durable-store conformance, bounded reconciliation, mailbox attention, and later harness smoke tests."
type: guide
tags: [v0.x, engineering, testing, agents]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T20:50:00+08:00
---

# v0.x testing and agent workflow

## Quality goals

- Test the public CLI contract rather than private Python function names.
- Test durable-store semantics independently from the built-in file layout.
- Prove that concurrent local writers cannot corrupt or lose successful durable state.
- Prove that delivery acknowledgement and unresolved attention remain independent.
- Prove that routine reconciliation reads only new or unresolved bounded context rather than accumulated task history.
- Keep core tests hermetic. They must not touch real zxro, acpx, Pi, Claude, or optional external providers.
- Make failures diagnosable with ordinary files, exit codes, stdout, and stderr.

## Test layers

| Layer | Purpose | Isolation | Required in CI |
|---|---|---|---|
| CLI contract | Exercise commands through `subprocess` and verify output, exit codes, and observable state | Temporary `$ZXRO_HOME`; no external commands unless faked | Yes |
| Durable-store conformance | Exercise work, turn, artifact, delivery, read ack, handled state, idempotency, isolation, and crash-recovery semantics through one provider boundary | Fresh provider namespace per test | Built-in provider: yes; optional adapters: opt-in |
| Built-in artifact invariants | Exercise locking, atomic replacement, JSON/JSONL parsing, event-generation rules, and artifact reference safety | Temporary directories and concurrent Python processes | Yes |
| Context-cost invariants | Verify bounded summaries, delta-only unread reads, bounded pending attention, and metadata-only routine inspection | Synthetic large artifacts in a temporary home | Yes |
| Manual smoke | Walk the CLI with Unix utilities and inspect files directly | Disposable local home | Before integration milestones |
| Storage-adapter smoke | Confirm a candidate external CLI satisfies the same behavior without leaking provider commands into callers | Disposable external-provider namespace | When evaluating an adapter |
| Harness smoke | Confirm real acpx + Pi/Claude integrations call the same CLI contract | Disposable sessions and target repos | After core CLI is stable |

## Required checks

```sh
python3 -m unittest discover -s tests -v
```

No `pytest`, Bats, testcontainers, or other third-party test dependency is required in v0.x.

Useful manual commands may include:

```sh
export ZXRO_HOME="$(mktemp -d)"
zxro watchtower create main --cwd "$PWD"
zxro work create smoke --watchtower main
find "$ZXRO_HOME" -type f -print
python3 -m json.tool "$ZXRO_HOME/work/smoke.json"
```

`jq` may be used by a developer if installed, but core tests and documented recovery procedures must not require it.

## Durable-store conformance cases

The same semantic cases should be runnable against the built-in provider and any optional adapter composition.

At minimum, verify:

- duplicate watchtower and work IDs are rejected predictably;
- unknown ownership references fail without creating partial logical records;
- current work reads are bounded and do not replay historical artifact bodies;
- work can be filtered by watchtower and state;
- turn creation records work, watchtower, agent, session name, and target cwd as separate identities;
- settlement is idempotent for the same logical completion;
- conflicting terminal settlements fail deterministically;
- artifact resolution is explicit and routine reads return references rather than bodies;
- two or more concurrent settlements produce no lost successful writes, stable event IDs, and unique ordered mailbox generations;
- `inbox unread` returns only generations greater than the current read ack;
- read ack cannot move backwards or advance beyond the highest known generation;
- advancing read ack past an unhandled event does not remove that event from `inbox pending`;
- `inbox pending` returns actionable unhandled events regardless of read cursor position;
- events may be handled out of generation order;
- handling the same event twice is idempotent;
- handling one event does not handle adjacent generations or close the work item;
- a crash after terminal turn commit but before mailbox publication can be retried into exactly one matching event;
- a mailbox event is never visible when its referenced terminal turn result is missing;
- separate zxro homes or equivalent provider namespaces do not collide;
- event and turn summaries reject or deterministically handle content beyond the 1,000-character v0.x bound;
- a large settlement payload is stored as an artifact or external evidence and is not copied into the inbox event;
- `work show`, `turn show`, `turn list`, `inbox unread`, `inbox pending`, and `inspect` do not inline artifact contents;
- machine output remains deterministic and errors use stable non-zero behavior.

The conformance suite should target an internal provider interface or a provider-neutral fixture, not hard-code `~/.zxro/work/*.json` paths except in tests specifically for the built-in file provider.

## Delivery and attention fixture

The test suite should exercise the distinction introduced by [decision 0002](../../decisions/0002-separate-delivery-from-attention.md).

A fixture should:

1. publish actionable events at generations 1, 2, and 3;
2. read all three through `inbox unread`;
3. ack through generation 3;
4. verify all three still appear in `inbox pending`;
5. handle generation 3's event first;
6. verify generations 1 and 2 remain pending;
7. handle generation 1;
8. verify generation 2 remains pending;
9. repeat handle for generation 1 and verify no new state is created;
10. verify `work close` has not been implied by any ack or handle operation.

This fixture catches the priority-loss bug where a monotonic read cursor accidentally doubles as completion state.

## Progressive-disclosure fixture

The test suite should include one synthetic long-running work item with many settled turns and at least one large artifact per turn. The test does not need realistic model output. Repeated text is enough.

The fixture proves this sequence:

1. Create and settle many turns.
2. Read and ack through generation N without handling every event.
3. Add one new settled turn at generation N+1.
4. Run `inbox unread` and verify that only generation N+1 appears.
5. Run `inbox pending` and verify it returns only bounded unresolved event envelopes, including any older unhandled events.
6. Verify that no artifact body appears in either mailbox view.
7. Run `work show`, `turn show`, and `inspect` and verify that they return metadata and bounded summaries only.
8. Resolve one artifact deliberately, then inspect a slice in the manual smoke test.

The point is not a microbenchmark. The contract is structural: `unread` output scales with new delivery, while `pending` scales with unresolved bounded events. Neither scales with old artifact bytes.

## Crash-gap fixture

Provider composition may split terminal turn state and mailbox publication across different systems. The test suite must exercise that gap without requiring a distributed transaction.

A fixture should:

1. persist artifacts;
2. commit the terminal turn with its allocated event ID;
3. simulate interruption before mailbox publication;
4. retry the settlement/reconciliation path;
5. verify exactly one mailbox event exists with that event ID;
6. retry again and verify event ID and generation do not change;
7. verify the newly published event begins unhandled.

This test is required for the built-in provider path and for any external adapter composition that cannot commit turn state and mailbox state atomically.

## Test data and isolation

Each built-in-provider test creates a temporary zxro home with `tempfile.TemporaryDirectory`. Tests spawn the real zxro CLI with a copied environment containing `ZXRO_HOME=<tempdir>`.

Concurrency tests use `multiprocessing`, `concurrent.futures`, or several subprocesses. They verify resulting logical state rather than assuming write order from process start order.

Tests must never depend on timestamps for uniqueness. Turn IDs use UUIDv4. Assertions should validate ordering fields and relationships instead of hard-coding generated IDs.

Optional provider integration tests must create a fresh provider namespace and must never reuse personal or production Beads/mail stores.

## Adapter evaluation

A candidate provider does not get special semantics because its native model differs from zxro. The adapter owns translation.

During evaluation, record separately:

- semantic conformance failures;
- whether the provider conflates read and handled/done state;
- operational requirements such as a daemon, server, database, tmux, or external binary;
- concurrency limits and whether adapter-side serialization is sufficient;
- namespace behavior and target-repository pollution;
- machine-output stability;
- features that are useful but outside zxro's required contract.

A candidate may be rejected for operational weight even if an adapter could technically make it conform.

## Agent workflow

Before Pi/Claude integration, agents working on zxro use the same CLI and tests as humans:

1. Read the task, architecture, durable-store contract, CLI spec, and nearby code.
2. Change the smallest coherent behavior.
3. Add or update black-box CLI and provider-conformance tests.
4. Run the full stdlib test suite.
5. Inspect representative built-in artifacts in a temporary home when the change affects durability.
6. Verify that routine read commands still expose bounded context rather than accumulated artifact bodies.
7. Verify ack and handle semantics remain independent when touching mailbox code.
8. Stop at documented human gates before making an optional external provider mandatory, adding a daemon, or embedding agent runtimes.

Integration code must remain thin. A Pi extension or Claude hook should invoke a documented zxro CLI command rather than duplicate persistence logic.

## Harness smoke tests

After the core CLI stabilizes:

- Pi: confirm `agent_settled` invokes `zxro turn settle` with inherited `ZXRO_*` metadata.
- Claude: confirm `Stop` and failure handling invoke `zxro turn settle` with the same metadata contract.
- acpx: confirm crew session names and cwd values remain independent from zxro work IDs.
- reconciliation: confirm a watchtower can ingest `inbox unread`, ack delivery, prioritize `inbox pending`, and fetch deeper evidence only when needed.
- storage adapter: confirm swapping one provider capability does not change the commands or metadata visible to the watchtower or harness hook.
- recovery: follow the native session recovery playbook without editing zxro state by hand.

These are manual or opt-in integration tests in v0.x. They do not belong in the dependency-free core CI suite until a reliable hermetic fixture exists.

## Related

- [Engineering index](./README.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [Decision 0002](../../decisions/0002-separate-delivery-from-attention.md)
- [Technology stack](../scope/technology-stack.md)
- [Implementation plan](../execution/implementation-plan.md)
- [v0.x CLI](../surfaces/cli.md)
