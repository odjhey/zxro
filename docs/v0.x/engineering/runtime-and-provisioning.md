---
name: v0x_runtime_and_provisioning
description: "Local v0.x runtime topology, zxro home layout, configuration, runtime-port boundary, and recovery posture without a daemon."
type: guide
tags: [v0.x, engineering, runtime]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T09:00:00+08:00
---

# v0.x runtime and provisioning

## Runtime topology

zxro v0.x has no resident process. Each CLI invocation reads and mutates durable artifacts under `$ZXRO_HOME`, then exits.

```text
human / watchtower / hook
          |
       zxro CLI
          |
     durable provider

agent execution remains separate:

watchtower or human
      |
  agent runtime port
      |
 acpx / native adapter
      |
  Pi / Claude
```

Later Pi and Claude integrations may invoke zxro at native completion boundaries, but zxro itself still does not stay resident.

The [agent runtime port](../../architecture/contracts/agent-runtime-port.md) is semantic. zxro does not need to proxy it in v0.x; a watchtower may invoke acpx directly.

## Ports and transports

zxro v0.x opens **no TCP port, UDP port, or Unix-domain socket**.

In architecture documents, `port` means a contract boundary. acpx/ACP/native harness transport is external to zxro. If a future adapter uses stdio, a Unix socket, or a daemon, that transport must preserve the same durable-store, session-binding, DATA/CONTROL, and exact-resume semantics.

Do not copy Rozoro's `monitor.sock` simply because it worked there. Rozoro needed a resident semantic owner; zxro's current CLI contract does not.

## Home layout

The initial built-in provider is intentionally inspectable. Its exact files remain an implementation choice behind the durable-store contract, but the expected shape is local and per-home:

```text
$ZXRO_HOME/
├── watchtowers/
├── work/
├── turns/
└── inbox/
```

Turn state contains the durable session binding when known. Large artifacts remain separate from routine work/turn/mailbox reads.

`ZXRO_HOME` defaults to `~/.zxro`.

## Process environment

A turn may propagate these variables to a child process:

```text
ZXRO_HOME
ZXRO_TURN_ID
ZXRO_WORK_ID
ZXRO_WATCHTOWER_ID
```

The turn record is authoritative. Environment variables exist so hooks and child processes can address that record without putting routing metadata into prompts.

Runtime/session identity is durable turn data, not an environment-variable naming scheme. Provider credentials may pass through to an external runtime but must not be copied into zxro state.

## Watchtower projects

Each watchtower has its own project cwd. The project may contain watchtower-specific `AGENTS.md`, Pi skills, prompts, and settings. That cwd is stored on the watchtower record.

Crew turns record their own target cwd independently. One watchtower may coordinate several unrelated repositories or worktrees at the same time.

## Environments

| Environment | Purpose | Provisioning | Data policy |
|---|---|---|---|
| Local | Primary v0.x runtime and manual experiment | Python 3.11+ checkout or installed script | Durable data under a user-owned `$ZXRO_HOME` |
| CI | Core CLI and artifact tests | Python 3.11+ only | Temporary zxro home; no real harness state |
| Hosted | Not supported in v0.x | None | None |

## Configuration and secrets

zxro core configuration comes from CLI arguments and `ZXRO_HOME`. It must not persist provider credentials or authentication tokens.

Agent-specific environment variables such as Claude profile or provider credentials may pass through a generic child-process helper later, but zxro must not copy their values into durable artifacts.

Session identifiers are data, not executable commands. zxro must not persist shell command strings as its resume contract.

## Atomicity and locking

The built-in provider follows the [durable store contract](../../architecture/contracts/durable-store.md):

- safe serialization is acceptable for concurrent writers;
- successful mutations must be durable on caller exit;
- IDs are validated before use as path/provider identifiers;
- unsafe symlinks, ownership, permissions, malformed state, and conflicts fail closed;
- settlement writes artifacts and terminal turn state before publishing the mailbox event;
- retry repairs the allowed terminal-state-without-event crash gap idempotently.

Provider-specific locking and fsync mechanics remain implementation details as long as those semantics hold.

## Observability

v0.x observability is intentionally local:

- CLI exit code;
- stderr diagnostic;
- optional JSON stdout;
- public current-state reads through `zxro work show`, `zxro turn list`, and `zxro turn show`;
- bounded mailbox reads through `zxro inbox unread` and `zxro inbox pending`;
- explicit evidence resolution through `zxro artifact path`.

The built-in provider's files may corroborate durability during diagnosis, but operators must not use their private format as the command interface. The joined `zxro inspect <work-id>` view is future M2 scope and is unavailable on `master`.

No metrics, traces, network health endpoint, or background health checks are required.

Runtime status comes from the external runtime port and remains distinct from zxro work acceptance or turn settlement.

## Failure and recovery

A wake notification is disposable. The mailbox event is not. Integrations persist the durable settlement before attempting a wake.

A session binding may help locate the underlying conversation, but recording an ID does not guarantee exact resume capability. When the normal path cannot continue, use the [native session recovery playbook](../../playbooks/native-session-recovery.md).

Exact resume must never silently become a cold start. If the runtime cannot prove the recorded conversation is resumable, fail and let the operator choose whether to create a new turn.

zxro must not rewrite Pi or Claude native transcripts during recovery.

## Related

- [Engineering index](./README.md)
- [Technology stack](../scope/technology-stack.md)
- [Product architecture](../../architecture/product-architecture.md)
- [Durable store](../../architecture/contracts/durable-store.md)
- [Session binding](../../architecture/contracts/session-binding.md)
- [Agent runtime port](../../architecture/contracts/agent-runtime-port.md)
- [Native session recovery](../../playbooks/native-session-recovery.md)
