---
name: v0x_testing_and_agent_workflow
description: "Dependency-free v0.x test strategy centered on black-box CLI behavior, artifact invariants, bounded reconciliation, and later harness smoke tests."
type: guide
tags: [v0.x, engineering, testing, agents]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:54:00+08:00
---

# v0.x testing and agent workflow

## Quality goals

- Test the public CLI contract rather than private Python function names.
- Prove that concurrent local writers cannot corrupt durable state.
- Prove that routine reconciliation reads only new bounded context rather than accumulated task history.
- Keep tests hermetic. They must not touch real zxro, acpx, Pi, Claude, or repository state.
- Make failures diagnosable with ordinary files, exit codes, stdout, and stderr.

## Test layers

| Layer | Purpose | Isolation | Required in CI |
|---|---|---|---|
| CLI contract | Exercise commands through `subprocess` and verify output, exit codes, and artifacts | Temporary `$ZXRO_HOME`; no external commands unless faked | Yes |
| Artifact invariants | Exercise locking, atomic replacement, JSON/JSONL parsing, generation rules, ack rules, and artifact reference safety | Temporary directories and concurrent Python processes | Yes |
| Context-cost invariants | Verify bounded summaries, delta-only inbox reads, and metadata-only routine inspection | Synthetic large artifacts in a temporary home | Yes |
| Manual smoke | Walk the CLI with Unix utilities and inspect files directly | Disposable local home | Before integration milestones |
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

`jq` may be used by a developer if installed, but tests and documented recovery procedures must not require it.

## Required CLI cases

At minimum, automate these behaviors before harness integration:

- duplicate watchtower and work IDs are rejected predictably;
- unknown watchtower and work references fail without creating partial artifacts;
- turn creation records the owning work, watchtower, agent, session name, and target cwd;
- settling a running turn records a result and appends exactly one inbox event;
- repeating the same settlement is idempotent, while conflicting settlement data fails deterministically;
- two or more concurrent settlements produce distinct ordered generations and parseable JSONL;
- `inbox pending` returns only generations greater than the current ack;
- ack cannot move backwards or advance beyond the highest known generation;
- event and turn summaries reject or deterministically handle content beyond the 1,000-character v0.x bound;
- a large raw settlement payload is stored as an artifact and is not copied into the inbox event;
- `work show`, `turn show`, `turn list`, `inbox pending`, and `inspect` do not inline artifact contents;
- `inspect` reports artifact references, counts, or byte sizes without reading their full text into stdout;
- `artifact path` resolves only artifacts beneath the active `$ZXRO_HOME` and rejects traversal or unsafe symlink escapes;
- adding a megabyte-scale artifact to an old turn does not change the output size of `inbox pending` when no new event references that content;
- acknowledged history is not replayed by `inbox pending` after later generations arrive;
- malformed JSON, invalid IDs, path traversal, unsafe symlinks, and ownership/permission violations fail closed where applicable;
- `--json` emits JSON on stdout without human decoration;
- command errors go to stderr and use stable non-zero exit codes.

## Progressive-disclosure fixture

The test suite should include one synthetic long-running work item with many settled turns and at least one large artifact per turn. The test does not need realistic model output. Repeated text is enough.

The fixture proves this sequence:

1. Create and settle many turns.
2. Ack through generation N.
3. Add one new settled turn at generation N+1.
4. Run `inbox pending` and verify that only generation N+1 appears.
5. Verify that no previous artifact body appears in stdout.
6. Run `work show`, `turn show`, and `inspect` and verify that they return metadata and bounded summaries only.
7. Resolve one artifact with `artifact path`, then inspect a slice with an ordinary Unix utility in the manual smoke test.

The point is not a microbenchmark. The contract is structural: routine output must not grow with the byte size of old artifacts.

## Test data and isolation

Each test creates a temporary zxro home with `tempfile.TemporaryDirectory`. Tests spawn the real zxro CLI with a copied environment containing `ZXRO_HOME=<tempdir>`.

Concurrency tests use `multiprocessing`, `concurrent.futures`, or several subprocesses. They verify resulting files rather than assuming write order from process start order.

Tests must never depend on timestamps for uniqueness. Turn IDs use UUIDv4. Assertions should validate ordering fields and relationships instead of hard-coding generated IDs.

## Agent workflow

Before M4/M5, agents working on zxro use the same CLI and tests as humans:

1. Read the task, architecture, CLI spec, and nearby code.
2. Change the smallest coherent behavior.
3. Add or update black-box CLI tests.
4. Run the full stdlib test suite.
5. Inspect representative artifacts in a temporary home when the change affects durability.
6. Verify that routine read commands still expose bounded context rather than accumulated artifact bodies.
7. Stop at documented human gates before adding dependencies, a daemon, or embedded agent runtimes.

Integration code must remain thin. A Pi extension or Claude hook should invoke a documented zxro CLI command rather than duplicate persistence logic.

## Harness smoke tests

After the core CLI stabilizes:

- Pi: confirm `agent_settled` invokes `zxro turn settle` with inherited `ZXRO_*` metadata.
- Claude: confirm `Stop` and failure handling invoke `zxro turn settle` with the same metadata contract.
- acpx: confirm crew session names and cwd values remain independent from zxro work IDs.
- reconciliation: confirm a watchtower can route from `inbox pending` without loading full historical artifacts, and fetches deeper evidence only when needed.
- recovery: follow the native session recovery playbook without editing zxro state by hand.

These are manual or opt-in integration tests in v0.x. They do not belong in the dependency-free core CI suite until a reliable hermetic fixture exists.

## Related

- [Engineering index](./README.md)
- [Technology stack](../scope/technology-stack.md)
- [Implementation plan](../execution/implementation-plan.md)
- [v0.x CLI](../surfaces/cli.md)
