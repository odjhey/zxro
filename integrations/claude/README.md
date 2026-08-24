# Claude Code settlement hook

This adapter settles one existing zxro turn when Claude Code reports a terminal
turn. It uses the public `zxro turn settle` command. It does not inspect Claude
transcripts or zxro storage.

## Supported events

The adapter targets Claude Code 2.1.241 and its documented command hook schema.
It accepts these terminal meanings:

- `Stop` becomes `completed` only when `background_tasks` and `session_crons`
  are present and empty.
- `StopFailure` becomes `failed` when `error` is one of the documented error
  types.
- `SessionEnd` with `reason: prompt_input_exit` becomes `cancelled`. Other
  session-end reasons do not describe cancellation and fail closed.

Claude Code does not fire `Stop` for a user interrupt. It also does not define a
terminal cancellation event for every interrupt path. Do not broaden the
`SessionEnd` matcher or infer cancellation from transcript text.

The hook requires inherited `ZXRO_TURN_ID` and `ZXRO_HOME`. The dispatcher must
create the turn and export both values before starting Claude. The payload's
session ID and cwd are validation fields, not zxro identity.

## Install

Install zxro so `zxro` is on Claude Code's `PATH`. Merge the `hooks` object from
`settings.example.json` into the target repository's `.claude/settings.json`.
The example uses Claude Code's documented exec form and
`${CLAUDE_PROJECT_DIR}` placeholder, so hook fields never enter a shell command.

The default configuration does not retain the raw hook payload. To retain it as
an zxro artifact, add `"--retain-payload"` to each hook's `args` array. The
mailbox contains only its bounded settlement message and artifact reference.

Hook errors go to stderr and return nonzero. `StopFailure` ignores command hook
exit status by design, but Claude Code still runs the command and zxro records a
successful settlement. Check Claude debug output and zxro state when diagnosing
that event.

## Tests

Run the hermetic adapter suite:

```sh
python3 -m unittest discover -s integrations/claude/tests -v
```

The suite uses a fake executable for argv, timeout, signal, and malformed-input
cases. One test invokes the repository's real zxro CLI in a disposable home to
check retry idempotency and artifact isolation.

Run the unchanged core gate separately:

```sh
python3 -m unittest discover -s tests -v
```

## Disposable harness smoke

This is opt-in because it needs acpx and working disposable Claude credentials.
Use a disposable repository and zxro home. Create a watchtower, work item, and
turn through zxro, then export the returned turn ID and run Claude through acpx
with the project hook installed:

```sh
export ZXRO_HOME="$PWD/.smoke-zxro"
export ZXRO_TURN_ID="$(zxro turn create --work smoke --agent claude --session smoke --cwd "$PWD")"
acpx claude 'Reply with exactly: smoke complete'
zxro --json turn show "$ZXRO_TURN_ID"
zxro --json inbox unread --watchtower smoke
```

Create the `smoke` watchtower and work item before the turn. Compare the turn,
event ID, generation, status, source, message, and artifact references with a
manual `zxro turn settle` run in a second disposable home. Never reuse a real
crew turn for this check.
