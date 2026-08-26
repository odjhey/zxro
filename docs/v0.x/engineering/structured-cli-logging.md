---
name: v0x_structured_cli_logging
description: "User-facing contract for opt-in ZXRO CLI diagnostics, event output, redaction, correlation, and file retention."
type: guide
tags: [v0.x, engineering, cli, diagnostics]
status: draft
generated: "OpenAI GPT-5.4, 2026-08-25"
sources:
  - ref: ../execution/web-ui-plan.md
    credibility: primary
  - ref: ../surfaces/cli.md
    credibility: primary
  - ref: ../../../zxro/diagnostics.py
    credibility: primary
created_at: "2026-08-25T11:45:00+08:00"
updated_at: "2026-08-26T16:00:00+08:00"
---

# Structured CLI logging

ZXRO diagnostics are opt-in. Ordinary commands keep their existing stdout, stderr, exit codes, and durable-state behavior.

## Enable diagnostics

Set flags before the command:

```sh
zxro --log-level info --log-format jsonl --json work list
```

The available flags are:

| Flag | Values | Default |
|---|---|---|
| `--log-level` | `off`, `error`, `warning`, `info`, `debug` | `off` |
| `--log-format` | `human`, `jsonl` | `human` |
| `--log-file` | An explicit path outside `$ZXRO_HOME` | stderr |
| `--correlation-id` | 1 to 128 characters, starting with `A-Z`/`a-z`/`0-9` and followed by `A-Z`, `a-z`, `0-9`, `.`, `_`, `:`, or `-` | generated invocation context only |
| `--log-sensitive` | flag | disabled |

The environment equivalents are `ZXRO_LOG_LEVEL`, `ZXRO_LOG_FORMAT`, `ZXRO_LOG_FILE`, and `ZXRO_CORRELATION_ID`. A flag wins over its environment variable. ZXRO does not read a logging config file and does not honor generic `DEBUG` or `LOG_LEVEL` variables. There is no environment equivalent for `--log-sensitive`.

Invalid logging configuration exits with code 2 before ZXRO opens the selected home or provider state.

## Destinations and compatibility

Without `--log-file`, diagnostics go to stderr. `--log-file` sends structured diagnostics to that file while normal command stderr keeps its current behavior. Diagnostics never go to stdout. `--json` still controls only the command result.

With `jsonl` on stderr, every diagnostic line is one event object. Parser usage and error text is retained in a bounded, redacted `zxro.cli.arguments.invalid` event instead of being written as non-JSON stderr. With `--log-file`, the same sanitized parser event is written to the file while normal parser stderr remains unchanged. On a structured stderr failure, the ordinary human error line is replaced by the final event's stable error code. Human output is a bounded one-line operator format and uses the same event name and attributes.

Logging is best effort. A formatting, append, rotation, permission, or event-construction failure disables the selected sink. This single-sink CLI does not write a fallback warning to the command's stderr, so command stdout, stderr, exit code, and durable state remain unchanged. It does not retry a mutation, repair state, or create a fallback under `$ZXRO_HOME`.

## Event envelope

Each healthy event contains:

```json
{
  "log_schema_version": 1,
  "event_name": "zxro.provider.read.completed",
  "event_version": 1,
  "timestamp": "2026-08-25T03:45:00.123Z",
  "level": "info",
  "process": "cli",
  "invocation_id": "inv-opaque",
  "sequence": 2,
  "correlation": {"home": "fp-opaque"},
  "duration_ms": 1.2,
  "attributes": {"command": "work.list", "result_code": "success"}
}
```

Timestamps are UTC RFC 3339 values with millisecond precision. Durations use a monotonic clock and are never negative. The sequence starts at 1 and increments only for events admitted by the selected threshold. The terminal `zxro.cli.invocation.completed` event bypasses the level threshold, is emitted once, and is the last event. It carries `process_exit_code` and either `result_code` or `error_code`.

Non-terminal stage events never carry `process_exit_code`. Successful stages carry `result_code`; failed stages carry a stable `error_code`.

The initial core event names include invocation start and completion, argument and configuration rejection, command dispatch, provider read and mutation stages, state validation failure, settlement publication success or failure stages, artifact verification success or failure, and measured lock wait. `inbox pending` is logged as a mutation operation because the current provider may compact state. The CLI emits aggregate stage events, not one event per durable record.

A sink failure disables the sink silently instead of emitting an event; see [Destinations and compatibility](#destinations-and-compatibility).

## Levels

Thresholds are inclusive:

- `error` admits errors and the terminal event.
- `warning` admits warnings, errors, and the terminal event.
- `info` admits normal lifecycle events, warnings, errors, and the terminal event.
- `debug` admits all defined events.

`off` emits no structured events and is the default.

## Correlation and redaction

Every invocation has a process-local invocation ID. A supplied correlation ID is validated and copied to each event. Home and resource values use keyed process-local fingerprints by default. The same value correlates within one process without becoming a durable identifier. A file sink keeps its owner binding as filesystem metadata on the log family, not as an event field or extra family file.

Default diagnostics omit:

- argv values, current working directories, home paths, and raw durable records;
- prompts, summaries, stdin, artifact bodies, and raw stdout;
- environment values, session and native-session IDs.

Cookies, authorization data, credentials, and token material are not omitted; the key is kept and its value is replaced with `[REDACTED]` (see below).

Every event attribute passes the same bounded redaction normalizer before either formatter writes it. This applies to nested mappings and sequences, arbitrary payload keys, absolute Unix/Windows paths (including UNC and delimiter-embedded Unix forms), and values under snake-case, camel-case, kebab-case, or dotted path-like keys; human and JSONL output therefore share the same sanitized attributes. Prompt, summary, stdin/stdout, environment, session/native-ID, payload, and artifact-content fields are omitted by normalized key family. Password, authorization, cookie, API-key, token, secret, credential, and nested header fields are replaced with `[REDACTED]`. Non-finite numbers are normalized before strict JSON serialization. Sensitive mode may reveal raw ZXRO resource IDs in owner-only local diagnostics. It never disables path, content, credential, or token exclusions, and it ends when the process exits. Pattern redaction is incomplete. Do not treat a log as a proof that sensitive content is absent.

Logs are observations from one process. Durable records remain authoritative for settlement, publication, acknowledgement, handling, closure, and artifact evidence. Diagnostic evidence must not repair or replace those records.

## File retention

An explicit log file must be outside the physical `$ZXRO_HOME`, including when either path uses a symlink alias. The selected parent directory must be owned by the current user with exact mode `0700`; existing active and backup files must be regular, owned by the current user, and exact mode `0600`. An insecure pre-existing parent such as `0755` or log file such as `0644` is rejected before append, rotation, or command state access. ZXRO never chmods user files; the rejection is fail-closed with no log write. Each log family binds to one stable home fingerprint, so another home cannot append, prune, or rotate it.

The active file is `PATH`; backups are `PATH.1` through `PATH.4`. ZXRO never keeps a sixth family file. The sink stores its owner binding as filesystem metadata on the family files, not as an extra file or emitted event. Each log file is capped at 5 MiB. It rotates before an append would cross that limit, deletes `PATH.4`, and shifts the remaining files under sink concurrency control.

Retention is file-granular and activity-triggered:

- on sink open and before every append, ZXRO removes a whole file only when its newest event is older than seven days;
- a mixed-age file stays when its newest event is recent, even if it contains older events;
- no file changes while the sink is inactive;
- one event must fit the bounded per-event size and cannot create a sixth file.

Deleting or rotating diagnostics never changes `$ZXRO_HOME`.

A process crash can stop the stream before `zxro.cli.invocation.completed`; a partial stream without a terminal event is expected in that case. The durable provider records remain authoritative, and the next invocation observes and reports their state normally. The test-only `ZXRO_FAULT_EXIT_AFTER` matrix exercises this crash exception at settlement boundaries.

## Examples

Human diagnostics to stderr:

```sh
zxro --log-level info work show example
```

JSONL diagnostics in a file while keeping command output clean:

```sh
zxro --json --log-level info --log-format jsonl \
  --log-file "$HOME/.local/state/zxro/logs/home-fingerprint.jsonl" \
  work list
```

Use a correlation ID generated by a trusted wrapper, not by an HTTP request or untrusted task content:

```sh
zxro --log-level info --log-format jsonl \
  --correlation-id refresh-01JABC123 \
  --json turn list
```

## Related

- [CLI-first Web UI plan](../execution/web-ui-plan.md)
- [v0.x CLI](../surfaces/cli.md)
- [Runtime and provisioning](./runtime-and-provisioning.md)
- [Testing and agent workflow](./testing-and-agent-workflow.md)
