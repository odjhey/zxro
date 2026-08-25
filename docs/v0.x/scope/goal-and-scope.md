---
name: v0x_goal_and_scope
description: "v0.x outcomes, boundaries, users, and success criteria for proving the durable coordination loop before harness integration."
type: plan
tags: [v0.x, scope]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T09:00:00+08:00
---

# v0.x goal and scope

## Goal

v0.x must prove that zxro can keep stable work identities, turn records, and per-watchtower durable mailbox state with a dependency-free CLI. The first milestone is deliberately manual. An operator must be able to create artifacts, simulate turn completion, observe new delivery, acknowledge read position, prioritize unresolved attention, handle events independently, and recover native Pi or Claude sessions without any Pi extension, Claude hook, daemon, or embedded ACP runtime.

The same CLI must support progressive context disclosure. Long-running work may accumulate large reports and logs, but routine watchtower reconciliation must read only bounded event context unless the operator or watchtower deliberately fetches deeper evidence.

Storage behavior follows the [durable store contract](../../architecture/contracts/durable-store.md). The built-in provider is local and dependency-free, while optional work or mailbox adapters may be evaluated and adopted later without changing public zxro commands.

Once that contract is boring and testable, Pi and Claude integrations may call the same CLI commands automatically.

## Intended users

| User | Need | Expected outcome |
|---|---|---|
| Operator | Inspect and repair durable coordination state from a shell | Every state change can be reproduced and understood with zxro CLI commands and ordinary Unix tools |
| Watchtower author | Give one coordinator a stable mailbox while its crews work across several projects | A watchtower project remains separate from crew target cwd values, and routine updates do not replay accumulated handoffs |
| Shared-box operator | Keep unrelated operators or companies from sharing durable coordination state | Separate `$ZXRO_HOME` roots provide an explicit isolation boundary while each home may contain several cooperating watchtowers |
| Integration author | Publish a Pi or Claude completion without importing zxro internals | A native hook invokes the same documented CLI contract a human can run |
| Provider evaluator | Test Beads, a local mail CLI, or another store without redesigning zxro | Candidate tools are scored against one provider-neutral conformance contract |
| Future zxro maintainer | Change the implementation without breaking callers | CLI and durable-store contracts remain more stable than Python module internals or provider schemas |

## Success criteria

- [ ] A fresh `$ZXRO_HOME` can register multiple watchtower projects and at least one work item for each.
- [ ] Separate `$ZXRO_HOME` roots do not share watchtower, work, turn, mailbox, ack, or handled state.
- [ ] A work item can record several turns across different agents, session names, and cwd values.
- [ ] Settling a turn publishes exactly one actionable event with stable `event_id` and monotonic generation after the terminal turn result is durable.
- [ ] Duplicate settlement is idempotent and does not duplicate the event or generation.
- [ ] Concurrent settlements preserve all successful writes and distinct monotonic generations.
- [ ] `inbox unread` returns only events newer than the durable read-ack cursor.
- [ ] Read ack may advance past an unhandled event without removing that event from `inbox pending`.
- [ ] `inbox pending` returns unhandled actionable events regardless of read position.
- [ ] Events can be handled out of generation order and repeated handle is idempotent.
- [ ] `work close`, read ack, and event handling remain independent operations.
- [ ] Routine mailbox output is bounded by new or unresolved event context and does not inline old reports, transcripts, logs, diffs, or raw hook payloads.
- [ ] Event and turn summaries are bounded; larger content is stored as referenced per-turn artifacts.
- [ ] Current `work show`, `turn list`, and `turn show` commands expose metadata and references without replaying artifact bodies.
- [ ] Future M2 `inspect`, once implemented, preserves the same bounded behavior; it is unavailable on `master`.
- [ ] A caller can deliberately resolve an artifact and inspect only the slice it needs.
- [ ] A crash after terminal-state commit but before mailbox publication can be retried into exactly one matching event.
- [ ] A mailbox event is never visible when its referenced terminal turn result is missing.
- [ ] The built-in provider passes the durable-store conformance suite with Python stdlib tests.
- [ ] Optional provider adapters can be evaluated with the same semantics without becoming core dependencies.
- [ ] JSON output is suitable for scripts and errors remain on stderr with non-zero exit codes.
- [ ] A documented break-glass path can locate and resume underlying Pi and Claude conversations when zxro/acpx automation is unavailable.

## In scope

- Python 3.11+ stdlib-only core CLI and built-in provider.
- Filesystem-backed default artifacts under `$ZXRO_HOME`, default `~/.zxro`.
- Provider-neutral storage behavior and internal adapter boundaries.
- Multiple watchtowers inside one zxro home.
- Separate zxro homes as the v0.x durable-state isolation mechanism.
- Watchtower, work, turn, inbox event, event ID, generation, read ack, handled state, summary, and artifact-reference concepts.
- Progressive context disclosure for watchtower reconciliation.
- Stable JSON output for automation-oriented commands.
- Metadata propagation through `ZXRO_*` environment variables.
- Manual acpx use during validation.
- Optional future work/mail provider adapters that preserve the same CLI contract.
- Later Pi `agent_settled` and Claude `Stop`/failure integrations that reduce to existing zxro CLI calls.

## Out of scope

- A mandatory zxro daemon, server, scheduler, or background worker.
- A mandatory database, Beads installation, mail server, or other external storage product.
- ACP implementation or `acpx/runtime` embedding.
- Agent process hosting, session queueing, cancellation, or provider authentication.
- Watchtower reasoning, task decomposition, review policy, or acceptance policy.
- Worktree, branch, PR, CI, or merge orchestration.
- Company or organization objects inside zxro. `$ZXRO_HOME` is the v0.x isolation boundary.
- A Windows port for the built-in provider in v0.x. `fcntl` locking makes macOS/Linux the initial target.
- Automatic installation of Pi or Claude hooks before the CLI contract is validated manually.

## Assumptions and constraints

- A watchtower has its own project directory. Its crews may target unrelated repositories or worktrees through each turn's `cwd`.
- Several watchtowers may coexist inside one `$ZXRO_HOME` when sharing durable state is intentional.
- Separate companies, customers, operators, or experiments should use separate zxro homes when their durable state must not mix.
- acpx is the initial agent-session client but is not a zxro dependency for core CLI tests.
- Native coding-agent stores remain authoritative for conversation transcripts.
- zxro stores references to sessions for recovery, not copies of provider transcripts.
- Large turn evidence stays behind per-turn artifact references. Routine mailbox and inspection commands return bounded summaries, metadata, and references.
- Delivery/read position and attention handling are distinct durable concepts.
- Optional provider dependencies remain optional. The base zxro CLI continues to work without them.
- v0.x uses UUIDv4 for turn IDs because it is available in the Python standard library.

## Exit criteria

Move beyond the CLI-only milestone when the durable coordination loop has survived repeated manual use, concurrency tests, crash-gap tests, and out-of-order attention handling without hidden repair steps or repeated loading of accumulated handoff files. At that point, add Pi and Claude integration as thin producers of `zxro turn settle` events.

Off-the-shelf provider evaluation does not block that milestone. If a candidate fits later, adopt it behind an adapter and rerun the conformance suite rather than changing the watchtower or harness contract.

## Related

- [Scope index](./README.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [Decision 0002](../../decisions/0002-separate-delivery-from-attention.md)
- [Technology stack](./technology-stack.md)
- [Implementation plan](../execution/implementation-plan.md)
- [v0.x CLI](../surfaces/cli.md)
- [Release readiness](../validation/release-readiness.md)
