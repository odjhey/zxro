---
name: native_session_recovery
description: "Break-glass procedure for locating and resuming the native Pi or Claude conversation behind a zxro/acpx turn."
type: guide
tags: [playbooks, recovery, sessions, acpx, pi, claude]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
sources:
  - ref: https://github.com/openclaw/acpx/blob/main/docs/sessions.md
    credibility: primary
  - ref: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md
    credibility: primary
  - ref: https://code.claude.com/docs/en/cli-reference
    credibility: primary
stale_after: 2026-10-01
created_at: 2026-08-24T15:33:00+08:00
updated_at: 2026-08-25T09:00:00+08:00
---

# Native session recovery

Use this playbook only when the normal zxro/acpx path cannot continue a crew conversation and an operator needs to inspect or resume it directly in Pi or Claude Code.

Native session recovery is diagnostic. Do not rewrite zxro artifacts or native transcript files by hand unless a separate recovery procedure explicitly requires it.

## Before recovery

Identify the zxro turn:

```sh
zxro turn show <turn-id>
```

Record:

- agent;
- crew target cwd;
- acpx session name;
- optional `native_session_id` if zxro already captured one.

If the turn ID is unknown, start from the work item with commands available on `master`:

```sh
zxro work show <work-id>
zxro turn list --work <work-id>
zxro turn show <turn-id>
```

`zxro inspect <work-id>` is a future M2 command and is unavailable on `master`.

## Ask acpx first

acpx keeps several identities. Only `agentSessionId` is provider-native.

```sh
acpx --cwd <crew-cwd> --format json <agent> sessions show <session-name>
```

If acpx is not installed globally, run a reviewed, pinned release without changing the project:

```sh
npx --yes acpx@0.13.1 --cwd <crew-cwd> --format json <agent> sessions show <session-name>
```

In JSON output, look for:

```json
{
  "acpxRecordId": "...",
  "acpSessionId": "...",
  "agentSessionId": "..."
}
```

The default text output labels `acpSessionId` as `sessionId`. This text label is still the ACP protocol session ID, not the provider-native ID. Some other acpx 0.13.1 JSON commands label the same value `acpxSessionId`, so identify the value by the command and meaning rather than spelling alone.

Do not pass `acpxRecordId`, `acpSessionId`, the text `sessionId`, or JSON `acpxSessionId` to Pi or Claude. Use `agentSessionId` only when present.

If acpx does not expose a native ID, use the provider-specific picker below.

## Stop acpx control

Do not open a native client while an acpx prompt can still write to the conversation. Let the current acpx prompt finish normally. If it cannot finish, cancel it cooperatively with the same cwd, agent, and session name:

```sh
acpx --cwd <crew-cwd> <agent> cancel --session <session-name>
```

With the pinned package:

```sh
npx --yes acpx@0.13.1 --cwd <crew-cwd> <agent> cancel --session <session-name>
```

Wait for the process running the original prompt to exit. Then close acpx control and confirm the public session metadata reports `closed: true`:

```sh
acpx --cwd <crew-cwd> <agent> sessions close <session-name>
acpx --cwd <crew-cwd> --format json <agent> sessions show <session-name>
```

Record the actual terminal outcome in zxro. Do not report a cancellation as completion. Use one of these commands as appropriate:

```sh
zxro turn settle <turn-id> --source operator --status completed --message "acpx turn completed before native recovery"
zxro turn settle <turn-id> --source operator --status failed --message "acpx turn failed before native recovery"
zxro turn settle <turn-id> --source operator --status cancelled --message "acpx turn cancelled before native recovery"
```

Confirm `zxro turn show <turn-id>` reports the same terminal state and settlement before starting Pi or Claude. If acpx does not close or the zxro outcome is unknown, stop. Do not guess and do not start native takeover.

## Pi recovery

Pi stores sessions under `~/.pi/agent/sessions/`, grouped by working directory. `pi-acp` uses Pi's normal session persistence and keeps its own small mapping under `~/.pi/pi-acp/`.

### Easiest path

Run the native picker from the crew target project:

```sh
cd <crew-cwd>
pi -r
```

Select the matching conversation. In an opened Pi session, `/session` shows the session ID and session file.

### Resume a known Pi session

Pi uses `--session`, not `--resume <id>`, for a specific ID or file:

```sh
cd <crew-cwd>
pi --session <session-id-or-file>
```

A partial UUID is accepted when it resolves unambiguously.


## Claude Code recovery

Use the same Claude profile environment that created the session. For installations with a custom profile, set `CLAUDE_CONFIG_DIR` before every recovery command.

### Easiest path

Run the official resume picker from the crew target project:

```sh
cd <crew-cwd>
claude --resume
```

Claude Code's picker can select a saved session. Current Claude Code also accepts a session name, so a known native name may be enough even when the UUID is not.

### Resume a known Claude session

```sh
cd <crew-cwd>
claude --resume <session-id-or-name>
```

Claude Code accepts both IDs and names. Current releases search beyond the current project when a concrete session ID is supplied, but the crew cwd remains useful context and should still be used.

### Prefer the native picker over transcript parsing

Do not make zxro depend on Claude's private transcript directory layout. If acpx does not expose `agentSessionId`, use `claude --resume` rather than scraping internal files.

## When to capture a native ID in zxro

If an integration receives a provider-native session ID from acpx or the native hook, it may persist it on the turn's session reference:

```json
{
  "agent": "claude",
  "session": "coder-auth",
  "native_session_id": "..."
}
```

This is a recovery hint, not zxro identity. The `work_id` and `turn_id` remain stable even if the native session is replaced.

## Concurrency warning

Do not keep a native Pi or Claude interactive process actively writing the same conversation while acpx is also driving it unless the provider explicitly supports that attachment model.

For break-glass takeover:

1. complete the [acpx stop and zxro settlement steps](#stop-acpx-control);
2. open the native session;
3. inspect or intervene;
4. exit the native client before returning control to acpx.

## Verification

Recovery succeeds when the native client shows the expected conversation history and target cwd without modifying zxro durable identity.

After recovery, re-check with commands available on `master`:

```sh
zxro turn show <turn-id>
zxro work show <work-id>
zxro turn list --work <work-id>
```

Do not use the future `zxro inspect <work-id>` example for this verification. It is unavailable on `master`.

Compare the before and after output. The work ID, turn ID, runtime, agent, session name, cwd, and optional native session ID must not change.

## Validation record

The command review on 2026-08-25 used:

- zxro master `a191ae7d00ed2d1974ab27581bda80b6346c8cde`;
- acpx 0.13.1 through `npx --yes acpx@0.13.1`;
- Pi 0.84.3;
- Claude Code 2.1.241.

The review confirmed the documented `zxro work show`, `zxro turn list --work`, `zxro turn show`, `zxro turn settle`, and acpx session, cancel, status, and close command forms from their help output. acpx 0.13.1 `sessions show --format json` returns `acpxRecordId`, `acpSessionId`, and `agentSessionId`. Its text output labels those first two fields `id` and `sessionId`. No provider session was needed to verify these CLI output paths.

The live native takeover checks remain blocked. This environment has no globally installed acpx executable and no disposable Pi or Claude credentials. The pinned npx package makes acpx available, but starting provider conversations would use an existing account and may incur charges. No provider conversation was started, no picker or known-ID resume was claimed, and no provider transcript or record was read or edited.

To complete validation, provision disposable Pi and Claude credentials, then run both picker and known-ID recovery from disposable target repositories. Capture the acpx `acpxRecordId`, `acpSessionId`, and `agentSessionId` fields from public JSON `sessions show` output. Pass only `agentSessionId` to the native client.

## Related

- [Playbooks](./README.md)
- [v0.x CLI](../v0.x/surfaces/cli.md)
- [Product architecture](../architecture/product-architecture.md)
