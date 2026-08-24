---
name: v0x_technology_stack
description: "Locked and deferred technology choices for the dependency-free zxro v0.x CLI, built-in store, and optional storage adapters."
type: reference
tags: [v0.x, scope, technology]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T16:31:00+08:00
---

# v0.x technology stack

## Locked choices

| Area | Choice | Rationale | Decision record |
|---|---|---|---|
| Core language | Python 3.11+ | Fast iteration, strong stdlib support for filesystem/process tooling, and direct reuse of proven Rozoro-style durability patterns | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Dependencies | Python standard library only | The base CLI must run from a checkout without dependency installation and remain easy to replace later | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| CLI parsing | `argparse` | Included in Python and sufficient for a small hierarchical CLI | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Storage behavior | [Durable store contract](../../architecture/contracts/durable-store.md) | Work, turn, artifact, mailbox delivery, read ack, attention handling, concurrency, crash recovery, and progressive disclosure are product semantics rather than filesystem semantics | — |
| Built-in current-state records | JSON files | Human-readable default provider with no database dependency | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Built-in mailbox event stream | Append-only JSONL | Immutable ordered local delivery with ordinary-tool inspection and replay | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Built-in mailbox read state | Small monotonic ack record per watchtower | Keeps delivery position cheap and independent from attention state | [0002](../../decisions/0002-separate-delivery-from-attention.md) |
| Built-in mailbox attention state | Separate event-ID keyed handled records | Allows out-of-order handling without rewriting immutable events or abusing the read cursor | [0002](../../decisions/0002-separate-delivery-from-attention.md) |
| Large evidence | Per-turn files referenced from bounded records | Keeps routine watchtower context independent from accumulated report and log size | — |
| Provider adapters | Internal adapters behind the durable-store contract | Allows Beads, a local mail CLI, or another provider to replace part of the built-in store without changing public zxro commands | — |
| Isolation | Separate `$ZXRO_HOME` roots | One home may contain many cooperating watchtowers; unrelated companies, customers, operators, or experiments can use separate durable-state roots | — |
| Built-in concurrency | `fcntl.flock`, atomic temp-file writes, `fsync`, `os.replace` | Prevent partial writes and serialize concurrent local writers on macOS/Linux | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| IDs | `uuid.uuid4()` | Available in the stdlib and sufficient for unique turn/event IDs in v0.x | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Automated tests | `python3 -m unittest` plus stdlib subprocess/tempfile helpers | Black-box CLI and provider-conformance tests without a test-framework dependency | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Agent session client | acpx CLI, outside zxro core | ACP session creation, persistence, queueing, resume, and cancellation already exist outside zxro | — |

The JSON/JSONL layout is the first built-in provider, not the architecture contract. Public zxro behavior must remain stable if a later adapter stores the same logical objects elsewhere.

## Integration languages

The zxro core remains Python. Integration code follows the host harness:

| Integration | v0.x implementation | Role |
|---|---|---|
| Pi | Small TypeScript extension using Node built-ins | Observe `agent_settled` and invoke zxro CLI |
| Claude Code | Command hook configuration, with zxro CLI as the command | Observe `Stop` or failure and invoke zxro CLI |

Neither integration may import private zxro Python modules. The CLI is the integration boundary.

Storage adapters are internal zxro implementation code. Optional adapters may invoke an external CLI, but provider-specific commands and schemas must not leak into Pi, Claude, or watchtower instructions.

## Provisional choices

| Area | Candidate | Validation needed |
|---|---|---|
| Work-store adapter | Beads or another local work CLI | Score against the durable-store conformance suite, especially namespace selection, bounded reads, external metadata, and 10 to 12 concurrent callers |
| Mailbox adapter | Local headless mail/inbox CLI | Require compact unread reads, stable event identity, read ack separate from handled state, retained history, idempotent publication, and separate body/artifact retrieval |
| Agent execution helper | Generic `zxro turn run <id> -- <command...>` | Add only if manually exporting `ZXRO_*` variables becomes noisy during the CLI experiment |
| Native session capture | Persist optional `native_session_id` when acpx or a hook exposes it | Verify Pi and Claude behavior across supported adapter versions |
| Watchtower wake | Best-effort acpx prompt after durable inbox append | Add only after manual unread/ack/pending/handle behavior is proven |

## Deferred choices

- Go, Rust, or TypeScript rewrite of the core.
- `acpx/runtime` embedding.
- Making Beads, a mail product, SQLite, or another store mandatory.
- Daemon/socket architecture for zxro itself.
- Hosted service or remote transport.
- Windows locking and path semantics for the built-in provider.
- zxro-specific full-text search or log slicing. v0.x resolves artifact references and relies on deliberate readers when deeper evidence is needed.

A compiled rewrite or provider swap is an implementation change, not a v0.x product goal. Revisit them after the CLI and durable-store contracts have matured through real use.

## Constraints

- Core zxro commands and the built-in provider must run with Python 3.11+ and no third-party packages.
- Optional adapters may have their own dependencies, but those dependencies must not become prerequisites for the built-in CLI.
- v0.x targets macOS and Linux.
- JSON modes must keep stdout machine-readable. Diagnostics go to stderr.
- Routine read commands must not inline large artifact bodies. Inbox events and summaries remain bounded and refer to larger evidence by opaque reference.
- Every provider composition must preserve settlement ordering and idempotency without requiring a distributed transaction.
- Every mailbox provider must preserve the separation between delivery/read position and handled attention, natively or through its adapter.
- Filesystem mutations in the built-in provider must reject unsafe paths, symlinks where ownership matters, malformed JSON, and conflicting state rather than guessing.
- Tests must use temporary homes and must not touch real zxro, acpx, Pi, Claude, or repository state unless running an explicit integration suite.
- acpx, Pi, Claude, and optional storage providers are validation dependencies for later integration tests only, not core unit-test dependencies.

## Related

- [Goal and scope](./goal-and-scope.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [Decision 0002](../../decisions/0002-separate-delivery-from-attention.md)
- [Testing and agent workflow](../engineering/testing-and-agent-workflow.md)
- [Implementation plan](../execution/implementation-plan.md)
- [Runtime and provisioning](../engineering/runtime-and-provisioning.md)
- [Decision 0001](../../decisions/0001-v0-cli-first-python-stdlib.md)
