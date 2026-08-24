---
name: v0x_goal_and_scope
description: "v0.x outcomes, boundaries, users, and success criteria for proving the durable artifact loop before harness integration."
type: plan
tags: [v0.x, scope]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:54:00+08:00
---

# v0.x goal and scope

## Goal

v0.x must prove that zxro can keep stable work identities, turn records, and per-watchtower durable inbox state with a dependency-free CLI. The first milestone is deliberately manual. An operator must be able to create artifacts, simulate turn completion, inspect pending events, acknowledge generations, and recover native Pi or Claude sessions without any Pi extension, Claude hook, daemon, or embedded ACP runtime.

The same CLI must support progressive context disclosure. Long-running work may accumulate large reports and logs, but routine watchtower reconciliation must read only new bounded event context unless the operator or watchtower deliberately fetches deeper evidence.

Once that contract is boring and testable, Pi and Claude integrations may call the same CLI commands automatically.

## Intended users

| User | Need | Expected outcome |
|---|---|---|
| Operator | Inspect and repair durable coordination state from a shell | Every state change can be reproduced and understood with zxro CLI commands and ordinary Unix tools |
| Watchtower author | Give one coordinator a stable inbox while its crews work across several projects | A watchtower project remains separate from crew target cwd values, and routine updates do not replay accumulated handoffs |
| Shared-box operator | Keep unrelated operators or companies from sharing durable coordination state | Separate `$ZXRO_HOME` roots provide an explicit isolation boundary while each home may contain several cooperating watchtowers |
| Integration author | Publish a Pi or Claude completion without importing zxro internals | A native hook invokes the same documented CLI contract a human can run |
| Future zxro maintainer | Change the implementation without breaking callers | CLI and artifact contracts remain clearer and more stable than Python module internals |

## Success criteria

- [ ] A fresh `$ZXRO_HOME` can register multiple watchtower projects and at least one work item for each.
- [ ] Separate `$ZXRO_HOME` roots do not share watchtower, work, turn, inbox, or ack state.
- [ ] A work item can record several turns across different agents, session names, and cwd values.
- [ ] Settling a turn appends exactly one ordered inbox event to its owning watchtower.
- [ ] Duplicate settlement is idempotent or fails deterministically without duplicating the inbox event.
- [ ] Concurrent settlements produce valid JSONL and distinct monotonic generations.
- [ ] `inbox pending` returns only events newer than the durable ack cursor.
- [ ] Routine reconciliation output is bounded by new event context and does not inline old reports, transcripts, logs, diffs, or raw hook payloads.
- [ ] Event and turn summaries are bounded; larger content is stored as referenced per-turn artifacts.
- [ ] `work show`, `turn show`, and `inspect` expose metadata and references without replaying artifact bodies.
- [ ] A caller can deliberately resolve an artifact path and inspect only the slice it needs with ordinary Unix tools.
- [ ] Ack cannot move backwards or past the known generation.
- [ ] Malformed, unsafe, or conflicting filesystem state fails closed.
- [ ] JSON output is suitable for scripts and errors remain on stderr with non-zero exit codes.
- [ ] The full CLI suite passes with `python3 -m unittest` using temporary zxro homes and no external service.
- [ ] A documented break-glass path can locate and resume underlying Pi and Claude conversations when zxro/acpx automation is unavailable.

## In scope

- Python 3.11+ stdlib-only CLI.
- Filesystem artifacts under `$ZXRO_HOME`, default `~/.zxro`.
- Multiple watchtowers inside one zxro home.
- Separate zxro homes as the v0.x durable-state isolation mechanism.
- Watchtower, work, turn, inbox, generation, ack, summary, and artifact-reference concepts.
- Progressive context disclosure for watchtower reconciliation.
- Stable JSON output for automation-oriented commands.
- Metadata propagation through `ZXRO_*` environment variables.
- Generic command execution with zxro metadata only after the core CRUD and inbox behavior are proven.
- Manual acpx use during validation.
- Later Pi `agent_settled` and Claude `Stop`/failure integrations that reduce to existing zxro CLI calls.

## Out of scope

- A zxro daemon, server, scheduler, or background worker.
- SQLite, Redis, or any other database.
- ACP implementation or `acpx/runtime` embedding.
- Agent process hosting, session queueing, cancellation, or provider authentication.
- Watchtower reasoning, task decomposition, review policy, or acceptance policy.
- Worktree, branch, PR, CI, or merge orchestration.
- Company or organization objects inside zxro. `$ZXRO_HOME` is the v0.x isolation boundary.
- A Windows port for v0.x. `fcntl` locking makes macOS/Linux the initial target.
- Automatic installation of Pi or Claude hooks before the CLI contract is validated manually.

## Assumptions and constraints

- A watchtower has its own project directory. Its crews may target unrelated repositories or worktrees through each turn's `cwd`.
- Several watchtowers may coexist inside one `$ZXRO_HOME` when sharing durable state is intentional.
- Separate companies, customers, operators, or experiments should use separate zxro homes when their durable state must not mix.
- acpx is the initial agent-session client but is not a zxro dependency for core CLI tests.
- Native coding-agent stores remain authoritative for conversation transcripts.
- zxro stores references to sessions for recovery, not copies of provider transcripts.
- Large turn evidence stays in per-turn artifacts. Routine inbox and inspection commands return bounded summaries, metadata, and references.
- v0.x uses UUIDv4 for turn IDs because it is available in the Python standard library.

## Exit criteria

Move beyond the CLI-only milestone when the durable artifact loop has survived repeated manual use and concurrency tests without requiring hidden repair steps or repeated loading of accumulated handoff files. At that point, add Pi and Claude integration as thin producers of `zxro turn settle` events. Consider a compiled implementation only after the artifact and CLI contracts have stabilized through real use.

## Related

- [Scope index](./README.md)
- [Technology stack](./technology-stack.md)
- [Implementation plan](../execution/implementation-plan.md)
- [v0.x CLI](../surfaces/cli.md)
- [Release readiness](../validation/release-readiness.md)
