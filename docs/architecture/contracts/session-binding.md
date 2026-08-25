---
name: session_binding_contract
description: "Durable contract for relating one zxro turn to an external runtime session and optional provider-native conversation identity."
type: contract
tags: [architecture, contracts, runtime, sessions, recovery]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
sources:
  - ref: https://github.com/odjhey/rozoro/blob/master/docs/plans/2026-08-22-000356-session-linking/plan.md
    credibility: primary
created_at: 2026-08-24T16:41:00+08:00
updated_at: 2026-08-25T18:36:18+08:00
---

# Session binding contract

## Purpose

A zxro turn may be executed through acpx, a native harness, or another runtime. zxro needs enough durable information to find that conversation again without confusing work identity with runtime identity.

Rozoro learned this the expensive way: task identity, pane/runtime identity, and harness conversation identity are different things. zxro keeps the same separation but does not inherit Rozoro's Herdr-specific descriptor or launch commands.

## Identities

The durable identity chain is:

```text
work_id       logical job
turn_id       one delegated execution
runtime       namespace that owns the external session
session       runtime-level session address
native id     optional provider-owned conversation identity
```

`work_id` and `turn_id` belong to zxro. Runtime and native identifiers do not.

A turn's runtime binding is the combination of fields already needed to address its execution:

```json
{
  "runtime": "acpx",
  "agent": "claude",
  "session": "coder-auth",
  "cwd": "/Users/example/src/app-wt/auth",
  "native_session_id": "9b92...",
  "native_session_source": "acpx.agentSessionId"
}
```

`native_session_id` and `native_session_source` are optional. They are recovery hints, not zxro identity.

## Invariants

1. A work ID never derives from cwd, runtime session name, process ID, or native session ID.
2. A turn ID never changes when more session metadata becomes known.
3. `runtime` names the namespace in which `session` is meaningful. A bare session string without its runtime is not a complete address.
4. `cwd` is the crew target recorded on the turn. It is not the watchtower project cwd.
5. A native session identity may be discovered after the turn starts and attached later without changing work or turn identity.
6. Repeating the same binding update is idempotent. A conflicting native identity for the same turn fails closed rather than silently replacing the old conversation.
7. Recording a native session ID does **not** prove that exact resume is supported by the current runtime or harness version.
8. Runtime/session updates never reopen closed work, mark mailbox events handled, or imply operator acceptance.
9. A late runtime fact cannot reactivate a closed work item. Durable runtime evidence and work acceptance remain separate axes.

If a workflow deliberately abandons one conversation and starts another, create a new turn instead of rewriting the old turn's binding.

## Binding lifecycle

### At turn creation

The caller should record the address it already knows:

```text
runtime
agent
session
cwd
```

For the first zxro use case, `runtime=acpx` and `session` is the acpx session name.

### After runtime discovery

If acpx or the harness later exposes a provider-native conversation ID, zxro may enrich the existing turn with:

```text
native_session_id
native_session_source
```

The public CLI needs a safe way to do this without editing provider files by hand. The intended command is:

```sh
zxro turn bind <turn-id> \
  --native-session-id <id> \
  --source acpx.agentSessionId
```

This is an enrichment operation, not a relink-to-anything command. Conflicting identity requires a new turn or an explicit future migration procedure.

When the native ID is already known at turn creation, the existing `--native-session-id` input remains valid. Such a turn may lack provenance. One later bind may add `native_session_source` when it repeats the same native ID. A different ID conflicts.

The command validates both values before taking the home lock. Each value must contain 1 to 256 characters and must not contain control characters. An unknown turn exits with class 3. Malformed input exits with class 2. Once both fields exist, a bind succeeds only when both values match. A different ID or source exits with conflict class 4 and leaves the record unchanged.

Binding is allowed while a turn is running, after settlement, and after its work closes. The implementation changes only `native_session_id` and `native_session_source` under the home lock. It does not change the work ID, turn ID, runtime address, cwd, lifecycle state, settlement, artifacts, or mailbox data.

## Resume rule

Exact resume is a runtime capability, not a property inferred from stored text.

The safe contract is:

```text
known binding + runtime says exact resume supported
    -> resume the same conversation

missing binding / unsupported capability / ambiguous identity
    -> fail with a precise reason
```

Never silently turn `resume` into `start new`.

zxro should not persist shell command strings or provider-specific resume argv as the durable contract. The runtime adapter owns invocation syntax. zxro stores identity and provenance; the adapter decides whether that identity is currently resumable.

## Provenance

`native_session_source` is a bounded, free provenance string, not a provider enum. Examples include:

```text
acpx.agentSessionId
pi.session
claude.session
manual
```

The source helps an operator understand whether an ID came from a public adapter surface or manual recovery. It must not contain credentials, transcript bodies, or arbitrary command text.

## Safety

- Treat runtime and native identifiers as data, never shell fragments.
- Reject control characters and unsafe values before passing identifiers to a runtime adapter.
- Do not persist provider credentials.
- Do not scan unrelated provider stores merely because a different harness lacks identity.
- If several native conversations are plausible, fail rather than guess.

## Relationship to the durable-store contract

A durable provider stores these fields as part of the turn's bounded current state. The provider does not need to understand acpx or any native harness.

The [agent runtime port](./agent-runtime-port.md) consumes the binding. The [durable store contract](./durable-store.md) remains authoritative for work/turn persistence, settlement, mailbox, crash safety, and progressive disclosure.

## Related

- [Durable store](./durable-store.md)
- [Agent runtime port](./agent-runtime-port.md)
- [Native session recovery](../../playbooks/native-session-recovery.md)
- [Ubiquitous language](../ubiquitous-language.md)
