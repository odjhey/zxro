---
name: c1_per_turn_artifacts_task_card
description: "Task card for ZR4: zxro artifact put with kind-unique references, evidence frozen at settlement, per-turn cap, and bounded-read regression tests."
type: checklist
tags: [v0.x, execution, task-cards, artifacts]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-25T14:25:09+08:00"
---

# C1 — Multiple artifacts per turn

Implements ZR4 from the [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md).

## Outcome

A caller attaches independently addressable evidence to a running turn with `zxro artifact put <turn-id> --kind <kind> --stdin`, references stay stable as `artifact:<turn-id>:<kind>`, the evidence set freezes at settlement, and routine reads stay bounded no matter how large the evidence grows.

## Inputs and dependencies

- No card blocks this one. First card in lane C; [C2](./c2-work-brief.md) stacks on its storage generalization.
- Runs in parallel with lanes A, B, and D. Use the A1 envelope-tolerant test helper for JSON assertions.
- The storage work must leave room for an owner scope in references (C2 introduces `artifact:work:<work-id>:brief`); do not hard-code turn ownership into the reference parser or on-disk layout.

## In scope

- `artifact put` for `running` turns; `turn settle --stdin` keeps writing its payload artifact through the same path.
- `kind` follows existing identifier rules and is unique per turn; a duplicate fails with exit class 4, no overwrite.
- Rejection of `artifact put` on settled turns (evidence set frozen) with exit class 4.
- Per-payload bound matching settlement today (16 MiB durable-record limit, roughly 8 MiB payload); per-turn cap of 32 artifacts at exit class 2.
- References and byte counts in `turn show` and settlement events; `artifact path` remains the retrieval step with existing digest and safety checks.
- Tests: multiple kinds on one turn, duplicate kind, put after settle, cap, reference visibility, digest verification, and the Scenario C bounded-read regression (growing an old artifact does not grow `inbox unread` or `work show` output).

## Out of scope

- External references per turn; deferred to the [A2](./a2-namespaced-work-metadata.md) metadata mechanism when extended to turn records.
- Post-settlement evidence attachment (ZR5 territory).
- Any `artifact cat`-style routine body read.

## Contract

| Produces | Consumes | Must not change |
|---|---|---|
| `artifact put` command; multi-artifact turns; owner-scope-ready reference handling | Artifact store; turn lifecycle states; identifier rules | Reference opacity for callers; progressive disclosure; settlement ordering; existing `--stdin` settlement behavior |

## Steps

1. Generalize artifact storage for multiple kinds per turn with an extensible owner scope.
2. Add the command with lifecycle, uniqueness, cap, and bound enforcement.
3. Surface references in turn and event output; add all listed tests.
4. Update the durable store contract's artifact section and the CLI spec.

## Acceptance criteria

- [ ] One turn holds several artifacts of distinct kinds, each independently resolvable.
- [ ] Evidence set is immutable after settlement.
- [ ] Scenario C regression passes: routine read output size is independent of stored artifact bytes.
- [ ] All failure modes hit their documented exit classes deterministically.

## Verification

```sh
python3 -m unittest discover -s tests -v
printf 'report body' | bin/zxro artifact put <turn-id> --kind review --stdin
printf 'log body'    | bin/zxro artifact put <turn-id> --kind test-log --stdin
bin/zxro turn show <turn-id>   # two references, byte counts, no bodies
```

## Documentation impact

- [ ] Durable store contract and CLI spec updated in this PR.
- [ ] ZR4 marked delivered in the delivery plan.

## Human gate

Contract compatibility review for the artifact-grammar groundwork (owner scope) that C2 will rely on.

## Related

- [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md)
- [C2 work brief](./c2-work-brief.md)
- [Task-card index](./README.md)
