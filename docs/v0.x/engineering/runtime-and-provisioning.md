---
name: v0x_runtime_and_provisioning
description: "Local v0.x runtime topology, zxro home layout, configuration, and recovery posture without a daemon."
type: guide
tags: [v0.x, engineering, runtime]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:33:00+08:00
---

# v0.x runtime and provisioning

## Runtime topology

zxro v0.x has no resident process. Each CLI invocation reads and mutates durable artifacts under `$ZXRO_HOME`, then exits.

```text
human / watchtower / hook
          |
       zxro CLI
          |
     $ZXRO_HOME

agent execution remains separate:

watchtower or human
      |
    acpx CLI
      |
  Pi / Claude
```

Later Pi and Claude integrations may invoke zxro at native completion boundaries, but zxro itself still does not stay resident.

## Home layout

The initial layout is intentionally inspectable:

```text
$ZXRO_HOME/
├── watchtowers/
│   └── <watchtower-id>.json
├── work/
│   └── <work-id>.json
├── turns/
│   └── <turn-id>/
│       ├── turn.json
│       └── result.json
└── inbox/
    └── <watchtower-id>/
        ├── events.jsonl
        └── ack
```

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

## Atomicity and locking

- Replace current-state JSON files with write-to-temp, `fsync`, and `os.replace`.
- Serialize append-only inbox writes with `fcntl.flock`.
- `fsync` event files before reporting success.
- Validate IDs before constructing paths.
- Reject symlinks and unsafe ownership/permissions where zxro relies on path integrity.
- Treat malformed artifacts as errors. Do not repair them by guessing.

## Observability

v0.x observability is intentionally local:

- CLI exit code;
- stderr diagnostic;
- optional JSON stdout;
- current-state JSON files;
- append-only inbox JSONL;
- `zxro inspect <work-id>` for a joined human-readable view.

No metrics, traces, or background health checks are required.

## Failure and recovery

A wake notification is disposable. The inbox event is not. Integrations must append the durable event before attempting to wake a watchtower.

If zxro or acpx state is insufficient to continue a conversation, use the [native session recovery playbook](../../playbooks/native-session-recovery.md). zxro must not rewrite Pi or Claude native transcripts during recovery.

## Related

- [Engineering index](./README.md)
- [Technology stack](../scope/technology-stack.md)
- [Product architecture](../../architecture/product-architecture.md)
- [Native session recovery](../../playbooks/native-session-recovery.md)
