---
name: v0x_cli
description: "Command contract for the zxro v0.x dependency-free CLI, including artifact CRUD, settlement, inbox, ack, inspection, and metadata helpers."
type: spec
tags: [v0.x, surfaces, cli]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:33:00+08:00
updated_at: 2026-08-24T15:33:00+08:00
---

# v0.x CLI

## Purpose

The CLI is the first zxro product contract. A human must be able to create, inspect, settle, and reconcile every durable artifact before Pi or Claude integrations automate those same operations.

The CLI must run on Python 3.11+ with no third-party Python packages.

## Global behavior

```text
zxro [--home PATH] [--json] <command> ...
```

- `$ZXRO_HOME` defaults to `~/.zxro`; `--home` overrides it for one invocation.
- Human-readable output is the default.
- `--json` reserves stdout for one valid JSON value. Diagnostics go to stderr.
- Mutating commands return non-zero on malformed, conflicting, or unsafe state.
- IDs supplied by users are validated before they become path components.
- A command must not silently create a missing parent artifact unless its contract says so.

## Watchtower commands

### `zxro watchtower create`

Register a stable watchtower identity and the project directory from which that watchtower loads its orchestration instructions.

```sh
zxro watchtower create main \
  --cwd ~/watchtowers/main \
  --agent pi \
  --session watchtower
```

Required:

- positional `id`
- `--cwd PATH`

Optional:

- `--agent NAME`
- `--session NAME`

The cwd is the watchtower project, not a default crew target.

### `zxro watchtower show`

Show one watchtower record.

```sh
zxro watchtower show main
zxro --json watchtower show main
```

This is the first place an operator checks the watchtower project cwd and optional runtime address.

### `zxro watchtower list`

List registered watchtowers.

```sh
zxro watchtower list
```

The human form should fit on one line per watchtower. JSON returns structured records.

## Work commands

### `zxro work create`

Create a stable logical work item owned by a watchtower.

```sh
zxro work create auth-fix --watchtower main
```

A work ID survives several coder, reviewer, tester, or scout turns. zxro must not derive it from cwd, branch name, or a native session ID.

### `zxro work show`

Show one work record and its direct ownership metadata.

```sh
zxro work show auth-fix
```

Detailed joined history belongs in `zxro inspect` rather than `work show`.

### `zxro work list`

List known work, optionally filtered by watchtower.

```sh
zxro work list
zxro work list --watchtower main
```

### `zxro work close`

Mark a logical work item closed after the watchtower or operator accepts the outcome.

```sh
zxro work close auth-fix
```

Closing work does not delete turns, inbox events, or native agent sessions.

## Turn commands

### `zxro turn create`

Create one delegated execution and return its generated UUID.

```sh
zxro turn create \
  --work auth-fix \
  --agent claude \
  --session coder-auth \
  --cwd ~/src/app-wt/auth
```

Required:

- `--work WORK_ID`
- `--agent NAME`
- `--session NAME`
- `--cwd PATH`

Optional:

- `--native-session-id ID` when a provider-native conversation ID is already known

The command resolves `watchtower_id` from the work record and persists it on the turn. `turn.cwd` is the crew target and remains independent from the watchtower project cwd.

Initial state is `running`.

### `zxro turn show`

Show one turn, including its zxro identities, crew target, session address, lifecycle state, and native ID when known.

```sh
zxro turn show 550e8400-e29b-41d4-a716-446655440000
```

This command is the preferred zxro-side starting point for native session recovery.

### `zxro turn list`

List turns, optionally filtered by work or state.

```sh
zxro turn list --work auth-fix
zxro turn list --work auth-fix --state settled
```

### `zxro turn settle`

Record the terminal outcome of one delegated turn and append exactly one durable event to the owning watchtower inbox.

```sh
zxro turn settle <turn-id> \
  --source manual \
  --status completed \
  --message "Implementation finished; focused tests pass."
```

Hook-oriented form:

```sh
zxro turn settle <turn-id> \
  --source claude \
  --status completed \
  --stdin
```

Supported status values for v0.x:

- `completed`
- `failed`
- `cancelled`

`--stdin` stores the producer payload or message needed for later diagnosis. Provider-specific payloads must not change the common inbox envelope.

Settlement rules:

- A successful first settlement writes the result before publishing the inbox event.
- Repeating an identical settlement is idempotent and must not create another generation.
- A conflicting second settlement fails deterministically.
- Settling an unknown turn fails without creating an inbox event.

Pi `agent_settled` and Claude `Stop`/failure integrations will call this command later. They do not get a separate persistence API.

### `zxro turn env`

Optional convenience command for the manual experiment. Print the zxro metadata environment for a turn without launching anything.

```sh
zxro turn env <turn-id>
```

Shell output may look like:

```sh
export ZXRO_TURN_ID='...'
export ZXRO_WORK_ID='auth-fix'
export ZXRO_WATCHTOWER_ID='main'
export ZXRO_HOME='/Users/example/.zxro'
```

JSON mode returns the same key/value pairs as data. The turn artifact remains authoritative.

### `zxro turn run`

Optional second-slice helper. Execute an arbitrary command with the turn's `ZXRO_*` metadata in its environment.

```sh
zxro turn run <turn-id> -- acpx --cwd ~/src/app-wt/auth claude -s coder-auth "Do the work"
```

This command must remain agent-agnostic. It does not parse acpx output or settle the turn automatically in the CLI-first milestone.

## Inbox commands

### `zxro inbox pending`

Return durable events newer than the watchtower's current ack cursor.

```sh
zxro inbox pending --watchtower main
zxro --json inbox pending --watchtower main
```

Each event includes at least:

```json
{
  "generation": 7,
  "type": "turn_settled",
  "watchtower_id": "main",
  "work_id": "auth-fix",
  "turn_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent": "claude",
  "created_at": "2026-08-24T15:33:00+08:00"
}
```

The full turn result remains in the turn artifact. Inbox entries are routing records, not copies of entire transcripts.

### `zxro ack`

Advance a watchtower's durable acknowledgement cursor.

```sh
zxro ack --watchtower main --through 7
```

Rules:

- ack may advance only to an existing generation;
- ack may not move backwards;
- repeating the current ack is allowed;
- ack never deletes inbox history.

## Inspection

### `zxro inspect`

Join the records an operator usually needs when diagnosing one work item.

```sh
zxro inspect auth-fix
zxro --json inspect auth-fix
```

Human output should include:

```text
work: auth-fix
watchtower: main
watchtower cwd: /Users/example/watchtowers/main

turns:
  <uuid>  claude  coder-auth     /repo/a  settled
  <uuid>  claude  reviewer-auth  /repo/a  running
  <uuid>  pi      scout-api      /repo/b  settled

inbox:
  highest generation: 7
  ack: 6
  pending: 1
```

`inspect` is read-only. It must not reconcile, ack, repair, or resume anything.

## Manual full-loop example

```sh
export ZXRO_HOME="$(mktemp -d)"

zxro watchtower create main --cwd ~/watchtowers/main --agent pi --session watchtower
zxro work create smoke --watchtower main

TURN="$(zxro turn create --work smoke --agent claude --session coder-1 --cwd /tmp/acpx-test)"

# Run the worker manually with zxro identity in the environment.
# turn env or turn run may reduce this boilerplate once implemented.
ZXRO_TURN_ID="$TURN" \
ZXRO_WORK_ID=smoke \
ZXRO_WATCHTOWER_ID=main \
acpx --cwd /tmp/acpx-test claude -s coder-1 "Inspect the repository."

zxro turn settle "$TURN" --source manual --status completed --message "Worker returned."
zxro inbox pending --watchtower main
zxro ack --watchtower main --through 1
zxro inspect smoke
```

## Exit codes

Exact numeric codes may be finalized during implementation, but these classes must remain distinct:

- success;
- usage/validation error;
- missing artifact;
- conflict or invariant violation;
- unsafe/malformed durable state;
- child-process failure for optional `turn run`.

## Related

- [Surfaces index](./README.md)
- [Product architecture](../../architecture/product-architecture.md)
- [Implementation plan](../execution/implementation-plan.md)
- [Native session recovery](../../playbooks/native-session-recovery.md)
