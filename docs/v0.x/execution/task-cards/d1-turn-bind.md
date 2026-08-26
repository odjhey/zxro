---
name: d1_turn_bind_task_card
description: "Task card for ZR3: the zxro turn bind command for late native-session-ID enrichment with idempotent, fail-closed semantics."
type: checklist
tags: [v0.x, execution, task-cards, sessions, recovery]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-25T18:36:18+08:00"
---

# D1 — Late session binding

Implements ZR3 from the [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md). The [session binding contract](../../../architecture/contracts/session-binding.md) already specifies the command; this card delivers the public implementation.

## Outcome

`zxro turn bind <turn-id> --native-session-id <id> --source <provenance>` enriches an existing turn with provider-native conversation identity after launch, idempotently and fail-closed, and the report's Scenario D passes: binding never changes work or turn identity.

## Inputs and dependencies

- No card blocks this one, and nothing stacks on it. Smallest card; a good first pick for a developer new to the codebase.
- Runs in parallel with lanes A, B, and C. Use the A1 envelope-tolerant test helper for JSON assertions.
- Unblocks practical native session recovery for the Pi (#16) and Claude (#15) integration paths.

## In scope

- The `turn bind` command with both flags required; a bind without provenance is rejected.
- Binding allowed on `running` and `settled` turns; it never touches settlement identity, mailbox state, or work lifecycle.
- Idempotent identical rebind; a different `native_session_id` on an already-bound turn fails with exit class 4 and changes nothing.
- Identifier validation as data: reject control characters, empty strings, and values over 256 characters with exit class 2; unknown turn fails with exit class 3.
- `native_session_id` and `native_session_source` visible in `turn show`, human and `--json`.
- Tests: idempotent rebind, conflicting rebind, bind after settle, unknown turn, malformed identifier, round-trip visibility.

## Out of scope

- Resume execution or resumability checks; the runtime adapter owns those.
- Any relink or migration path; replacing a conversation means a new turn.
- Changes to `turn create --native-session-id`, which stays valid for the known-at-creation case.

## Contract

| Produces | Consumes | Must not change |
|---|---|---|
| `turn bind` command; enriched turn records | Session binding contract invariants; turn store | Work and turn identity; settlement and mailbox semantics; closed-work behavior; provenance value rules |

## Steps

1. Add the command and identifier validation.
2. Implement idempotent and fail-closed binding under the home lock.
3. Expose the fields in `turn show`; add all listed tests.
4. Update the session binding contract's status note (implementation no longer missing) and the CLI spec.

## Acceptance criteria

- [x] Scenario D passes: identical rebind idempotent, conflict fails closed, identity unchanged, stored identity is data rather than resume syntax.
- [x] Binding a settled turn works and alters nothing besides the binding fields.
- [x] All failure modes hit their documented exit classes.

## Verification

```sh
python3 -m unittest discover -s tests -v
bin/zxro turn bind <turn-id> --native-session-id 9b92aa10 --source acpx.agentSessionId
bin/zxro turn bind <turn-id> --native-session-id 9b92aa10 --source acpx.agentSessionId  # idempotent
bin/zxro turn bind <turn-id> --native-session-id other-id --source acpx.agentSessionId; echo "exit=$?"  # 4
```

## Documentation impact

- [x] Session binding contract and CLI spec updated in this PR.
- [x] ZR3 marked delivered in the delivery plan.

## Human gate

None beyond standard review; the contract decisions were already accepted in the session binding contract.

## Related

- [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md)
- [Session binding contract](../../../architecture/contracts/session-binding.md)
- [Native session recovery playbook](../../../playbooks/native-session-recovery.md)
- [Task-card index](./README.md)
