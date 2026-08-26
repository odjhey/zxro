---
name: c2_work_brief_task_card
description: "Task card for ZR2: a set-once work-scoped brief artifact with work create --brief-stdin, work brief set, and work brief path."
type: checklist
tags: [v0.x, execution, task-cards, artifacts, work]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-26T06:30:00+08:00"
---

# C2 — Durable work brief

Implements ZR2 from the [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md).

## Outcome

The original request behind a work item survives session churn: a work item carries at most one immutable brief stored as a work-scoped artifact (`artifact:work:<work-id>:brief`), settable at create time or later while the work is open, retrievable only through a deliberate `work brief path` call.

## Inputs and dependencies

- Stacked on [C1](./c1-per-turn-artifacts.md): the owner-scoped artifact storage generalization must merge first. Implementation may proceed on a branch stacked on C1's.
- Runs in parallel with lanes A, B, and D. Use the A1 envelope-tolerant test helper for JSON assertions.
- Distinct from [A2](./a2-namespaced-work-metadata.md): the brief is evidence behind an artifact reference, not metadata; nothing here touches the metadata mechanism.

## In scope

- Reference grammar extension `artifact:work:<work-id>:brief`; the reference stays opaque to callers.
- `work create --brief-stdin` with atomicity: a failed brief write leaves no work record behind.
- `work brief set` (open work only, set-once; a second set fails with exit class 4) and `work brief path` (same symlink, ownership, and digest checks as `artifact path`).
- Payload bounds matching other artifacts.
- `work show` returns the brief reference and byte count, never the body.
- Tests: create with brief, create-with-brief atomicity, set-once conflict, closed-work rejection, brief unchanged through turns and close, bounded `work show`, digest-verified retrieval.

## Out of scope

- Brief mutation or versioning; corrections belong in turn artifacts or the bounded work summary. The brief is an immutable record of the original request and the measuring stick for B1 verdicts, not the current statement of the work (that is the summary). When a producer cannot honestly classify `done`, `partial`, or `blocked` against the brief, the work has become different work: open a new work item with a new brief.
- Any accumulated handoff document; this card exists to prevent one.
- Briefs on watchtowers or turns.

## Contract

| Produces | Consumes | Must not change |
|---|---|---|
| `--brief-stdin`, `work brief set|path`; work-scoped reference form | C1 owner-scoped artifact storage; work lifecycle | Work identity and state semantics; bounded routine reads; existing turn-scoped reference behavior |

## Steps

1. Extend the reference grammar and storage with the work owner scope on top of C1.
2. Add the create-time flag with atomic failure behavior, then the two subcommands.
3. Surface the reference in `work show`; add all listed tests.
4. Update the durable store contract's work and artifact sections and the CLI spec.

## Acceptance criteria

- [x] A brief set at creation is retrievable byte-identically after settlement bursts, work close, and process restarts.
- [x] Set-once, open-only, and atomic-create rules fail at their documented exit classes.
- [x] No routine read inlines the brief body.

## Verification

```sh
python3 -m unittest discover -s tests -v
printf 'Fix refresh-token expiry.' | bin/zxro work create auth-fix --watchtower main --brief-stdin
BRIEF=$(bin/zxro work brief path auth-fix) && cat "$BRIEF"
```

## Documentation impact

- [x] Durable store contract and CLI spec updated in this PR.
- [x] ZR2 marked delivered in the delivery plan.

## Human gate

Contract compatibility review for the reference-grammar extension.

## Related

- [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md)
- [C1 per-turn artifacts](./c1-per-turn-artifacts.md)
- [Task-card index](./README.md)
