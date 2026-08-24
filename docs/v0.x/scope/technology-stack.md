---
name: v0x_technology_stack
description: "Locked and deferred technology choices for the dependency-free zxro v0.x CLI and artifact store."
type: reference
tags: [v0.x, scope, technology]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:33:00+08:00
---

# v0.x technology stack

## Locked choices

| Area | Choice | Rationale | Decision record |
|---|---|---|---|
| Core language | Python 3.11+ | Fast iteration, strong stdlib support for filesystem/process tooling, and direct reuse of proven Rozoro-style durability patterns | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Dependencies | Python standard library only | The CLI must run from a checkout without dependency installation and remain easy to replace later | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| CLI parsing | `argparse` | Included in Python and sufficient for a small hierarchical CLI | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Durable records | JSON files | Human-readable current-state artifacts with no database dependency | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Durable event streams | Append-only JSONL | Supports ordered inspection with Unix tools and simple replay | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Concurrency | `fcntl.flock`, atomic temp-file writes, `fsync`, `os.replace` | Prevent partial writes and serialize concurrent local writers on macOS/Linux | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| IDs | `uuid.uuid4()` | Available in the stdlib and sufficient for unique turn IDs in v0.x | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Automated tests | `python3 -m unittest` plus stdlib subprocess/tempfile helpers | Black-box CLI tests without a test-framework dependency | [0001](../../decisions/0001-v0-cli-first-python-stdlib.md) |
| Agent session client | acpx CLI, outside zxro core | ACP session creation, persistence, queueing, resume, and cancellation already exist outside zxro | — |

## Integration languages

The zxro core remains Python. Integration code follows the host harness:

| Integration | v0.x implementation | Role |
|---|---|---|
| Pi | Small TypeScript extension using Node built-ins | Observe `agent_settled` and invoke zxro CLI |
| Claude Code | Command hook configuration, with zxro CLI as the command | Observe `Stop` or failure and invoke zxro CLI |

Neither integration may import private zxro Python modules. The CLI is the integration boundary.

## Provisional choices

| Area | Candidate | Validation needed |
|---|---|---|
| Agent execution helper | Generic `zxro turn run <id> -- <command...>` | Add only if manually exporting `ZXRO_*` variables becomes noisy during the CLI experiment |
| Native session capture | Persist optional `native_session_id` when acpx or a hook exposes it | Verify Pi and Claude behavior across supported adapter versions |
| Watchtower wake | Best-effort acpx prompt after durable inbox append | Add only after manual `inbox pending` and ack behavior is proven |

## Deferred choices

- Go, Rust, or TypeScript rewrite of the core.
- `acpx/runtime` embedding.
- SQLite or another indexed store.
- Daemon/socket architecture.
- Hosted service or remote transport.
- Windows locking and path semantics.

A compiled rewrite is an implementation change, not a v0.x product goal. Revisit it after CLI and artifact contracts have matured through real use.

## Constraints

- Core zxro commands must run with Python 3.11+ and no third-party packages.
- v0.x targets macOS and Linux.
- JSON modes must keep stdout machine-readable. Diagnostics go to stderr.
- Filesystem mutations must reject unsafe paths, symlinks where ownership matters, malformed JSON, and conflicting state rather than guessing.
- Tests must use temporary homes and must not touch real zxro, acpx, Pi, Claude, or repository state.
- acpx, Pi, and Claude are validation dependencies for later manual integration tests only, not core unit-test dependencies.

## Related

- [Goal and scope](./goal-and-scope.md)
- [Testing and agent workflow](../engineering/testing-and-agent-workflow.md)
- [Runtime and provisioning](../engineering/runtime-and-provisioning.md)
- [Decision 0001](../../decisions/0001-v0-cli-first-python-stdlib.md)
