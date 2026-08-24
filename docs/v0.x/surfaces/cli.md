---
name: v0x_cli
description: "Command contract for the zxro v0.x dependency-free CLI, including artifact CRUD, settlement, inbox, ack, inspection, and progressive context disclosure."
type: spec
tags: [v0.x, surfaces, cli]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:33:00+08:00
updated_at: 2026-08-24T15:54:00+08:00
---

# v0.x CLI

## Purpose

The CLI is the first zxro product contract. A human must be able to create, inspect, settle, and reconcile every durable artifact before Pi or Claude integrations automate those same operations.

The CLI must run on Python 3.11+ with no third-party Python packages.

Routine reads must also stay cheap for agents. zxro exposes small current-state records and references first. Large reports, logs, diffs, and other evidence are read only when a human or watchtower explicitly asks for them.

## Global behavior

```text
zxro [--home PATH] [--json] <command> ...
```

- `$ZXRO_HOME` defaults to `~/.zxro`; `--home` overrides it for one invocation.
- One `$ZXRO_HOME` may contain several watchtowers. Separate homes are the v0.x isolation boundary when companies, customers, operators, or experiments must not share durable zxro state.
- Human-readable output is the default.
- `--json` reserves stdout for one valid JSON value. Diagnostics go to stderr.
- Mutating commands return non-zero on malformed, conflicting, or unsafe state.
- IDs supplied by users are validated before they become path components.
- A command must not silently create a missing parent artifact unless its contract says so.
- Routine read commands must not inline historical artifact contents.

## Progressive disclosure contract

zxro uses a four-level read path for context management:

```text
Level 0  zxro inbox pending --watchtower <id>
         new bounded event envelopes only

Level 1  zxro work show <work-id>
         current work state and latest bounded context

Level 2  zxro turn show <turn-id>
         one turn's metadata, outcome, summary, and artifact references

Level 3  zxro artifact path <artifact-ref>
         local path to full evidence for deliberate inspection
```

A watchtower should make routing decisions at the shallowest level that contains enough evidence. It may use ordinary Unix tools such as `grep`, `sed`, or `tail` after resolving an artifact path. zxro does not automatically `cat` large artifacts into agent context.

Event and turn summaries are limited to 1,000 Unicode characters after normalization in v0.x. Content beyond that limit belongs in a referenced artifact.

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

List registered watchtowers in the active `$ZXRO_HOME`.

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

Show the current state of one work item without replaying its history.

```sh
zxro work show auth-fix
```

The response may include:

- work identity and owning watchtower;
- status and current or latest turn IDs;
- latest bounded summary;
- unresolved current references or blocker counts when zxro has them;
- highest related generation metadata.

It must not inline prior turn reports, raw hook payloads, transcripts, logs, diffs, or other artifact contents. Historical metadata belongs in `zxro inspect`; evidence stays behind artifact references.

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

Show one turn's zxro identities, crew target, session address, lifecycle state, bounded summary, artifact references, and native ID when known.

```sh
zxro turn show 550e8400-e29b-41d4-a716-446655440000
```

This command is the preferred zxro-side starting point for both deeper evidence inspection and native session recovery. It must not inline artifact contents or a full provider hook payload.

### `zxro turn list`

List turns, optionally filtered by work or state.

```sh
zxro turn list --work auth-fix
zxro turn list --work auth-fix --state settled
```

List output contains metadata only.

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

`--message` is the bounded routing summary. It must not exceed 1,000 Unicode characters after normalization.

`--stdin` stores the producer payload needed for later diagnosis as a turn artifact. Provider-specific payloads must not change the common inbox envelope, and raw stdin must not be copied into that envelope.

Settlement rules:

- A successful first settlement writes the result and any payload artifact before publishing the inbox event.
- Repeating an identical settlement is idempotent and must not create another generation.
- A conflicting second settlement fails deterministically.
- Settling an unknown turn fails without creating an inbox event.
- The inbox event contains bounded routing context and artifact references, never the full payload.

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

Each event is a bounded routing envelope. Example:

```json
{
  "generation": 7,
  "type": "turn_settled",
  "watchtower_id": "main",
  "work_id": "auth-fix",
  "turn_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent": "claude",
  "outcome": "completed",
  "summary": "Reviewer found one blocker in refresh-token expiry handling.",
  "artifacts": [
    {
      "ref": "turns/550e8400-e29b-41d4-a716-446655440000/review.md",
      "kind": "review",
      "bytes": 8921
    }
  ],
  "created_at": "2026-08-24T15:54:00+08:00"
}
```

`pending` returns only generations greater than the durable ack. It must not replay acknowledged generations, join previous turn reports, or inline artifact contents. The size of routine reconciliation therefore follows new pending work rather than accumulated work history.

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

## Artifact commands

### `zxro artifact path`

Resolve one artifact reference to its local path without printing the artifact contents.

```sh
zxro artifact path turns/550e8400-e29b-41d4-a716-446655440000/review.md
```

The returned path must remain under the active `$ZXRO_HOME` and pass zxro's path and symlink safety checks.

This is the explicit bridge to deeper inspection:

```sh
REPORT="$(zxro artifact path turns/550e8400-e29b-41d4-a716-446655440000/review.md)"
grep -n "blocker" "$REPORT"
tail -n 80 "$REPORT"
sed -n '120,180p' "$REPORT"
```

zxro deliberately does not make `artifact cat` part of the v0.x routine interface. A caller that wants a large artifact must choose how much to read.

## Inspection

### `zxro inspect`

Join the metadata an operator usually needs when diagnosing one work item.

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
  <uuid>  claude  coder-auth     /repo/a  settled   2 artifacts / 12.1K
  <uuid>  claude  reviewer-auth  /repo/a  running   0 artifacts
  <uuid>  pi      scout-api      /repo/b  settled   1 artifact / 3.8K

inbox:
  highest generation: 7
  ack: 6
  pending: 1
```

`inspect` is read-only. It must not reconcile, ack, repair, resume, or print artifact contents. Artifact counts, references, and byte sizes are acceptable; accumulated handoff text is not.

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
