# Pi settlement extension

This extension settles one inherited zxro turn when Pi 0.84.3 emits `agent_settled`. It reads the final assistant message through Pi's public session API. A `stop` result maps to `completed`, `error` maps to `failed`, and `aborted` maps to `cancelled`. Other stop reasons fail without calling zxro.

The extension requires an absolute `ZXRO_HOME` and a UUID in `ZXRO_TURN_ID`. The dispatcher must export both before it starts Pi. `ZXRO_EXECUTABLE` may select a zxro executable and defaults to `zxro`. `ZXRO_PI_TIMEOUT_MS` defaults to 10000 and may range from 1 to 300000.

## Install

Copy this directory to a trusted Pi extension location, or load it for one run:

```sh
pi -e /path/to/zxro/integrations/pi/index.ts
```

The extension executes an argv array equivalent to:

```text
zxro turn settle $ZXRO_TURN_ID --source pi --status STATUS --message SUMMARY --stdin
```

It does not invoke a shell. The stdin artifact contains the semantic event name, Pi stop reason, and optional error message. The bounded mailbox message contains no payload text. Pi reports adapter errors through its UI and extension error channel. Missing metadata, ambiguous outcomes, zxro errors, closed stdin, signals, and timeouts do not become successful settlements. On timeout, the adapter sends `SIGTERM` to the child process group, waits 100 ms, sends `SIGKILL` to the group, and reports failure only after the direct child closes and escalation finishes. Windows lacks POSIX process groups, so the adapter applies the same sequence to the direct child.

## Hermetic gate

Run from this directory with Node 24 or newer:

```sh
npm test
```

The tests use a fake zxro executable for argv, stdin, timeout, signal, and failure checks. One test invokes the repository's public CLI in a temporary `ZXRO_HOME` to check retry idempotency, event identity, generation, and artifact-only payload storage. No Pi package is installed for this gate.

## Disposable acpx and Pi smoke

Keep this opt-in. It needs `acpx`, Pi credentials, and disposable zxro state.

1. Create a disposable watchtower, work, and turn with the public zxro CLI.
2. Export that turn's UUID as `ZXRO_TURN_ID` and export the disposable absolute directory as `ZXRO_HOME`.
3. Dispatch a disposable Pi session through acpx with `index.ts` loaded. Ask it for a response that ends normally.
4. Run `zxro turn show "$ZXRO_TURN_ID"` and `zxro inbox unread --watchtower WATCHTOWER_ID`.
5. Compare the turn status, settlement event ID, mailbox generation, message, and artifact reference with a second disposable turn settled by the manual CLI form above.
6. Remove the disposable target repository, acpx session, and `ZXRO_HOME`.

Do not claim this smoke from the hermetic test. Record the installed acpx and Pi versions, exact commands, exit codes, turn IDs, event IDs, generations, and cleanup result.

See [SMOKE.md](SMOKE.md) for the reproducible command and evidence from the 2026-08-25 acpx 0.13.1 and Pi 0.84.3 run.
