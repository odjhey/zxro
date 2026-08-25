---
name: b1_structured_verdict_task_card
description: "Task card for the ZR1 structured routing verdict: optional --verdict and --needs on turn settle, retry identity, and mailbox envelope exposure."
type: checklist
tags: [v0.x, execution, task-cards, settlement, mailbox]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-25T14:51:24+08:00"
---

# B1 — Structured routing verdict

Implements ZR1 from the [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md); completes milestone MR's most important semantic gap.

## Outcome

`zxro turn settle` accepts an optional `--verdict done|ready|blocked` and a bounded `--needs` value, both join settlement retry identity, and mailbox event envelopes expose them so a watchtower makes its mechanical routing decision on fields, never on prose. The report's Scenario B passes end to end: `outcome=completed`, `verdict=blocked`.

## Inputs and dependencies

- The verdict vocabulary human gate must clear before implementation starts (see below).
- No card blocks this one; lane B runs in parallel with lanes A, C, and D. Use the A1 envelope-tolerant test helper for JSON assertions so merge order against A1 does not matter.
- Downstream consumers: the Pi (#16) and Claude (#15) integration PRs settle turns and should state how they will source a verdict; this card unblocks that decision.

## In scope

- `--verdict` with three fixed values answering one producer-locally knowable question, "can the work advance without something this turn could not provide": `done` (nothing left that this turn knows of), `ready` (more to do, nothing in the way), `blocked` (cannot advance without what `--needs` names). `--needs` is at most 1,000 Unicode characters after NFC normalization, same rule as `--message`. Both optional, stored as absent when omitted, no default derived from `--status`.
- The two scoping rules that keep the vocabulary honest: a verdict states durable work facts, never who acts next (routing is the watchtower's job, made from fields plus `--needs` judgment), and never runtime liveness (background tasks or subagents still running mean the producer must not settle yet, per requirement 13 of the requirements report, not settle with a hedged verdict).
- Extending settlement retry equality: an idempotent retry repeats verdict and needs exactly; a conflict fails with exit class 4, matching existing outcome/summary rules.
- `verdict` and `needs` on the settled turn record and in `inbox unread` / `inbox pending` envelopes when present.
- Downgrade note in conventions: older binaries reject verdict-carrying durable records with exit class 5.
- Tests: settle with and without verdict, retry equality including both fields, conflicting-verdict rejection, envelope exposure, needs-length bounds, Scenario B end to end.
- Durable store contract, CLI spec, and conventions updates in the same PR.

## Out of scope

- Deriving a verdict from `--status`.
- Vocabulary extensions; adding a value is a later contract change.
- Who-acts-next taxonomies or a `--needs-kind` enum; those encode routing conclusions the producer cannot know. If a live watchtower loop later shows constant `--needs` pattern-matching, add structure from those observed categories, not guessed ones.
- Settlement-timing enforcement in the harness integrations; the trustworthy-boundary rule lands with the Pi and Claude cards, and a premature settlement already fails loudly here as a retry-identity conflict.
- Changes to the Pi or Claude integrations themselves.
- Structured `inputs-needed` payloads beyond bounded text; larger content is a C1 artifact referenced from the turn.

## Contract

| Produces | Consumes | Must not change |
|---|---|---|
| `--verdict` and `--needs` flags; enriched settlement identity; enriched event envelopes | `turn settle` path; settlement idempotency rules; mailbox publication | Existing three execution outcomes; settlement ordering and crash-gap repair; envelope boundedness; behavior of verdict-less callers |

## Steps

1. Confirm the vocabulary sign-off, then add flag parsing and normalization.
2. Extend settlement identity and its conflict handling; cover the crash-gap retry path.
3. Expose both fields on turn records and mailbox envelopes.
4. Add tests, then update the three contract documents.

## Acceptance criteria

- [ ] Scenario B: a completed execution reports `verdict=blocked` and the fact is readable from `inbox pending` without parsing the summary.
- [ ] Verdict-less settlement behavior is byte-identical to today.
- [ ] Retry with different verdict or needs fails deterministically; identical retry is idempotent through the crash gap.
- [ ] New JSON fields are additive; no schema bump.

## Verification

```sh
python3 -m unittest discover -s tests -v
bin/zxro turn settle <turn-id> --source manual --status completed --verdict blocked \
  --needs "operator decision required" --message "Review done; one blocker."
bin/zxro --json inbox pending --watchtower <id>   # verdict field present
```

## Documentation impact

- [ ] Durable store contract, CLI spec, and conventions updated in this PR.
- [ ] ZR1 marked delivered in the delivery plan; implementation plan MR row evidence updated.

## Human gate

Maintainer sign-off on the verdict vocabulary (`done | ready | blocked`) before implementation, as named in the delivery plan; watchtower logic will switch on these strings. Acceptance test for the gate: classify ten real settlement situations using only what the settling process knew at the time; if two classifiers disagree on more than one, the vocabulary is underspecified.

## Related

- [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md)
- [Rozoro-derived requirements report](../../../reports/2026-08-25-rozoro-derived-requirements.md)
- [Task-card index](./README.md)
