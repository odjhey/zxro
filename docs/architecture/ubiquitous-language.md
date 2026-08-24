---
name: ubiquitous_language
description: "Canonical zxro terms for watchtowers, work, turns, runtime/session bindings, inbox events, and acknowledgement."
type: glossary
tags: [architecture, domain, terminology]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T16:41:00+08:00
---

# Ubiquitous language

Update terminology here before propagating it to contracts, plans, and code.

| Term | Definition | Not to be confused with |
|---|---|---|
| zxro | The durable identity, artifact, and mailbox layer for coordinated agent work | An agent runtime, ACP client, or watchtower |
| watchtower | A coordinator, usually a persistent Pi conversation, that decides what work should happen next | A zxro daemon or a crew session |
| watchtower project | The dedicated project directory from which a watchtower loads its own `AGENTS.md`, skills, prompts, and settings | A crew target repository or worktree |
| watchtower ID | Stable zxro address for one watchtower and its inbox | Native Pi/acpx session ID |
| work | A logical unit of work that may pass through several crew turns before completion | A single model turn or native session |
| work ID | Stable zxro identifier for one work item | Branch name, cwd, PR number, or provider session ID, though callers may choose similar human-readable text |
| crew | A coding-agent role or persistent conversation used to act on work, such as coder, reviewer, tester, or scout | The logical work item |
| turn | One delegated execution against a work item | A whole work item or a whole native agent session |
| turn ID | zxro-generated UUID for one delegated execution | ACP request ID or native provider session ID |
| crew cwd | The repository or worktree directory in which a crew turn operates | The watchtower project cwd |
| runtime | The external session namespace/adapter used to execute a turn, initially `acpx` | zxro durable-store provider |
| session binding | Durable address that relates one turn to its runtime, agent, session name, cwd, and optional native session identity | Work identity or proof that resume is supported |
| session address | Runtime + agent + runtime session name + crew cwd, with optional provider-native session identity | zxro work ID |
| native session ID | Provider-owned conversation identifier captured for recovery when available | acpx record ID or acpx session ID |
| runtime port | Semantic start/send/control/status/resume boundary implemented by acpx or another adapter | TCP/UDP port number or zxro listener |
| DATA | Free text intentionally delivered to the model conversation | Runtime control action |
| CONTROL | Closed runtime action executed by the adapter, such as interrupt or cancel | Chat text sent to the model |
| settle | Record that a delegated turn has reached its completion boundary and publish one durable inbox event | Closing or deleting the persistent agent session |
| inbox | Ordered durable event stream owned by one watchtower | The acpx prompt queue |
| generation | Monotonic sequence number assigned to an inbox event | Turn ID or process generation |
| ack | Highest inbox generation a watchtower has durably observed | Event handled state or agent acknowledgement |
| handled | Per-event durable state meaning this actionable event no longer needs watchtower attention | Read acknowledgement or work closure |
| wake | Best-effort notification that prompts a watchtower to inspect its durable inbox | The durable event itself |

## Identity hierarchy

```text
watchtower_id
  work_id
    turn_id
      session binding
        optional native session id
```

The first three identifiers belong to zxro. Runtime and native session identifiers belong to acpx or the coding harness.

## Metadata variables

zxro uses environment variables to propagate durable identity without adding routing metadata to the model prompt:

- `ZXRO_TURN_ID`
- `ZXRO_WORK_ID`
- `ZXRO_WATCHTOWER_ID`
- `ZXRO_HOME` when a non-default zxro home is required

The turn record remains authoritative. Environment variables are routing conveniences for hooks and child processes.

## Naming rules

- Use `watchtower_id`, `work_id`, and `turn_id` in data and code.
- Use `cwd` only with an explicit owner or record context. Do not treat watchtower cwd and crew cwd as interchangeable.
- Use `runtime` for the namespace/adapter in which a session name is meaningful.
- Use `native_session_id` only for provider-owned IDs. Never label an acpx record ID or acpx session ID as a native session ID.
- Recording a session ID never implies `resume_supported=true`; resume is a runtime capability.
- Use `settled` for the zxro turn lifecycle state. Do not use `done` to imply that the whole work item is accepted.
- Use `ack` for delivery observation and `handled` for resolved watchtower attention.
- Use `wake` for a disposable notification and `event` for the durable inbox record.

## Related

- [Product architecture](./product-architecture.md)
- [Session binding](./contracts/session-binding.md)
- [Agent runtime port](./contracts/agent-runtime-port.md)
- [v0.x CLI](../v0.x/surfaces/cli.md)
- [Native session recovery](../playbooks/native-session-recovery.md)
