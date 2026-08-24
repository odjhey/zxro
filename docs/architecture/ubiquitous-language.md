---
name: ubiquitous_language
description: "Canonical zxro terms for watchtowers, work, turns, sessions, inbox events, and acknowledgement."
type: glossary
tags: [architecture, domain, terminology]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:33:00+08:00
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
| session address | The agent name, acpx session name, cwd, and optional native session ID needed to locate a conversation | zxro work ID |
| native session ID | Provider-owned conversation identifier used for last-resort direct resume | acpx record ID or acpx session ID |
| settle | Record that a delegated turn has reached its completion boundary and publish one durable inbox event | Closing or deleting the persistent agent session |
| inbox | Ordered durable event stream owned by one watchtower | The acpx prompt queue |
| generation | Monotonic sequence number assigned to an inbox event | Turn ID or process generation |
| ack | Highest inbox generation a watchtower has durably consumed | Delivery attempt or agent acknowledgement |
| wake | Best-effort notification that prompts a watchtower to inspect its durable inbox | The durable event itself |

## Identity hierarchy

```text
watchtower_id
  work_id
    turn_id
      session address
```

The first three identifiers belong to zxro. Session identifiers belong to acpx or the native coding harness.

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
- Use `native_session_id` only for provider-owned IDs. Never label an acpx record ID as a native session ID.
- Use `settled` for the zxro turn lifecycle state. Do not use `done` to imply that the whole work item is accepted.
- Use `wake` for a disposable notification and `event` for the durable inbox record.

## Related

- [Product architecture](./product-architecture.md)
- [v0.x CLI](../v0.x/surfaces/cli.md)
- [Native session recovery](../playbooks/native-session-recovery.md)
