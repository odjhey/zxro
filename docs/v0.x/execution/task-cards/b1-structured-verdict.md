---
name: b1_structured_verdict_task_card
description: "Task card for the ZR1 structured routing verdict: optional --verdict and --needs on turn settle, retry identity, and mailbox envelope exposure."
type: checklist
tags: [v0.x, execution, task-cards, settlement, mailbox]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-25T19:15:39+08:00"
---

# B1 — Structured routing verdict

Implements ZR1 from the [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md); completes milestone MR's most important semantic gap.

## Outcome

`zxro turn settle` accepts an optional `--verdict done|partial|blocked` and a bounded `--needs` value, both join settlement retry identity, and mailbox event envelopes expose them so a watchtower makes its mechanical routing decision on fields, never on prose. The report's Scenario B passes end to end: `outcome=completed`, `verdict=blocked`.

## Inputs and dependencies

- The verdict vocabulary human gate must clear before implementation starts (see below).
- No card blocks this one; lane B runs in parallel with lanes A, C, and D. Use the A1 envelope-tolerant test helper for JSON assertions so merge order against A1 does not matter.
- Downstream consumers: the Pi (#16) and Claude (#15) integration PRs settle turns and should state how they will source a verdict; this card unblocks that decision.

## In scope

- `--verdict` with three fixed values, each a producer-local claim about the work measured against the brief (absent a brief, against the work summary and turn instructions): `done` (the brief's ask is met, as far as this turn can tell), `partial` (partly met or not yet met; work remains, nothing prevents it), `blocked` (cannot advance without what `--needs` names; takes precedence over `partial` when both are true). `--needs` is at most 1,000 Unicode characters after NFC normalization, same rule as `--message`. Both optional, stored as absent when omitted; absence means no claim was made. When unsure between `done` and `partial`, claim `partial`; when unable to classify, omit. No default derived from `--status`.
- The scoping rules that keep the vocabulary honest: every value must complete "the work is ..." (a verdict describes the work item, never the turn's own attempt, which is `--status`, and never the producer's uncertainty, which is omission); a verdict states durable work facts, never who acts next (routing is the watchtower's job, made from fields plus `--needs` judgment); and never runtime liveness (background tasks or subagents still running mean the producer must not settle yet, per requirement 13 of the requirements report, not settle with a hedged verdict). A verdict is a claim the watchtower verifies, not a fact it must trust: `done` never closes work by itself; acceptance stays with `work close`.
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

## Verdict transport guidance (non-normative)

Lifecycle signals carry no verdict information; hooks transport a verdict, they never derive one. So the integrations do not diverge, the recommended convention: the crewmate ends its final message with

```text
ZXRO-VERDICT: done|partial|blocked
ZXRO-NEEDS: <one line, only with blocked>
```

The hook extracts this with an exact match from the final assistant message (the Claude `Stop` payload already delivers `last_assistant_message`), validates the value against the enum, and drops to absent on anything missing or malformed. It never guesses. Two mechanical exceptions are honest without a marker: a small allowlist of operator-required failure reasons (account on hold, expired auth, exhausted quota) may settle `blocked` with a matching `--needs`, and a non-empty `background_tasks` at `Stop` means do not settle yet.
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

- [x] Scenario B: a completed execution reports `verdict=blocked` and the fact is readable from `inbox pending` without parsing the summary.
- [x] Verdict-less settlements omit both fields and retain the existing durable shape.
- [x] Retry with different verdict or needs fails deterministically; identical retry is idempotent through the crash gap.
- [x] New JSON fields are additive; no schema bump before A1 lands.

## Verification

```sh
python3 -m unittest discover -s tests -v
bin/zxro turn settle <turn-id> --source manual --status completed --verdict blocked \
  --needs "operator decision required" --message "Review done; one blocker."
bin/zxro --json inbox pending --watchtower <id>   # verdict field present
```

## Documentation impact

- [x] Durable store contract, CLI spec, and conventions updated in this PR.
- [ ] ZR1 marked delivered in the delivery plan after merge; implementation plan MR row evidence remains pending the complete MR milestone.

## Human gate

Cleared: the maintainer approved the verdict vocabulary `done | partial | blocked` on 2026-08-25 after adversarial review of alternatives. The binding coupling rule is: `blocked` requires non-empty `--needs`; `--needs` is rejected with `done`, `partial`, or an omitted verdict. This decision replaced the card's earlier wording that treated both inputs as independently optional.

The verdict remains a producer claim about work against the brief or summary. It does not close work, handle events, report liveness, or assign an actor.

## Related

- [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md)
- [Rozoro-derived requirements report](../../../reports/2026-08-25-rozoro-derived-requirements.md)
- [Task-card index](./README.md)
