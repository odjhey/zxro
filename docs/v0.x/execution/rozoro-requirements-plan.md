---
name: v0x_rozoro_requirements_plan
description: "Implementation-ready designs and delivery sequence for ZR1 (structured routing verdict), ZR2 (durable brief reference), ZR3 (late session binding), and ZR4 (multiple artifacts per turn)."
type: plan
tags: [v0.x, execution, settlement, artifacts, sessions, rozoro]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
sources:
  - ref: ../../reports/2026-08-25-rozoro-derived-requirements.md
    credibility: primary
  - ref: ../../architecture/contracts/durable-store.md
    credibility: primary
  - ref: ../../architecture/contracts/session-binding.md
    credibility: primary
created_at: "2026-08-25T13:10:00+08:00"
updated_at: "2026-08-25T18:34:06+08:00"
---

# ZR1-ZR4 delivery plan

## Purpose

The [Rozoro-derived requirements report](../../reports/2026-08-25-rozoro-derived-requirements.md) names four near-term gaps: ZR1 (structured routing verdict separate from execution outcome), ZR2 (durable original brief/source reference), ZR3 (late session/native-ID binding), and ZR4 (general multiple artifacts or external references per turn). This plan turns each into a design a developer can implement, and sequences them into PR-sized work packages with acceptance criteria mapped to the report's scenarios.

ZR5 (external event ingress) and ZR6 (joined `inspect`) stay out of scope here; the report defers them until a real producer or the M2 ergonomics milestone demands them.

## Shared constraints

Every design below must respect the invariants already published:

- routine reads stay bounded; no design may inline artifact bodies into work, turn, or inbox output ([durable store contract](../../architecture/contracts/durable-store.md));
- durable built-in-provider records fail closed on unknown fields, so each additive field carries the same downgrade posture as the M0/M1 boundary in [contract conventions](../../architecture/contracts/conventions.md#settlement-compatibility): an older binary rejects the enriched record with exit class 5;
- all new public `--json` fields are additive. Under the machine-contract design for issues #25 and #26, additive fields do not bump the schema version. These fields ship inside the version 1 envelope.

## ZR3: late session/native-ID binding

Smallest item first: the [session binding contract](../../architecture/contracts/session-binding.md) already specifies the command; only the public implementation is missing.

```sh
zxro turn bind <turn-id> \
  --native-session-id <id> \
  --source acpx.agentSessionId
```

Decisions:

- both flags are required; a bind without provenance is not accepted;
- binding is allowed on `running` and `settled` turns. Recovery after settlement is a normal case, and binding never changes settlement identity, mailbox state, or work lifecycle;
- repeating an identical bind is idempotent success. A different `native_session_id` for a turn that already has one fails with exit class 4 and changes nothing. Replacing a conversation means creating a new turn;
- identifiers are validated as data before persistence: reject control characters, empty strings, and values longer than 256 characters with exit class 2. `--source` uses the short provenance forms the contract lists;
- unknown turn fails with exit class 3.

Tests: idempotent rebind, conflicting rebind, bind after settle, unknown turn, malformed identifier, and round-trip visibility in `turn show` (human and `--json`).

## ZR4: multiple artifacts per turn

`artifact_refs` is already plural everywhere in the contracts; what is missing is a public way to attach evidence outside `turn settle --stdin`.

```sh
zxro artifact put <turn-id> --kind review --stdin
zxro artifact put <turn-id> --kind test-log --stdin
```

Decisions:

- `kind` follows the existing identifier rules and is unique per turn, so the existing reference form `artifact:<turn-id>:<kind>` stays stable. A duplicate kind fails with exit class 4; there is no overwrite;
- artifacts attach to `running` turns, and `turn settle --stdin` keeps writing its payload artifact through the same path. After settlement the turn's evidence set is frozen; a late external fact is ZR5 or work-level metadata territory (issue #26), not a mutation of settled evidence;
- per-payload bounds match settlement today (the built-in provider's 16 MiB durable-record limit, roughly 8 MiB of payload). A per-turn cap of 32 artifacts keeps envelopes and `turn show` output bounded; exceeding it fails with exit class 2;
- `turn show` and settlement events list references and byte counts only. `artifact path` remains the deliberate retrieval step;
- external references per turn (a PR URL, a CI run ID) are not a new mechanism: once issue #26's namespaced metadata lands, extending it to turn records is the intended shape. This package delivers artifacts only and records that decision.

Tests: multiple kinds on one turn, duplicate kind rejection, put after settle rejection, per-turn cap, reference visibility in `turn show` and settlement events, byte/digest verification through `artifact path`, and Scenario C's bounded-read check: growing an old artifact must not grow `inbox unread` or `work show` output.

## ZR1: structured routing verdict

Execution outcome and routing verdict answer different questions, so they become separate fields on settlement.

```sh
zxro turn settle <turn-id> \
  --source claude \
  --status completed \
  --verdict blocked \
  --needs "operator decision: keep or revert the expiry change" \
  --message "Review finished; one blocker recorded."
```

Decisions:

- `--verdict` takes `done`, `partial`, or `blocked`. A verdict is the producer's claim about the work measured against the brief (absent a brief, against the work summary and the turn's instructions): `done` claims the brief's ask is met as far as this turn can tell; `partial` claims the ask is partly met or not yet met, work remains, and nothing prevents it; `blocked` claims the work cannot advance without something named in `--needs`. `blocked` takes precedence when both `partial` and `blocked` are true. Every value must complete the sentence "the work is ...": verdicts describe the work item, never the turn's own attempt (that is `--status`) and never the producer's uncertainty (that is omission). It is optional; an omitted verdict is stored as absent and means no claim was made, matching the convention that writers omit absent values. When unsure between `done` and `partial`, claim `partial`; when unable to classify at all, omit. No default is derived from `--status`, because guessing `done` from `completed` would recreate the ambiguity ZR1 exists to remove;
- a verdict is a claim, not a fact: `done` means this turn believes nothing is left, and the watchtower verifies before acting on it. Acceptance stays with `work close`. A settlement event therefore means: check my work against the brief;
- earlier drafts used `done|waiting|needs-action|blocked` and then `done|ready|blocked`. `waiting` and `needs-action` were cut because they differ only in who acts next, a routing conclusion owned by the watchtower, not a fact the settling producer can know; `ready` was replaced because its plain reading ("it's ready") collides with `done`. Verdicts state durable work facts; the watchtower maps facts to routing, reading `--needs` when its judgment requires detail. Only the mechanical decision (advance, dispatch next, or stop and attend) must be field-driven;
- a verdict never encodes runtime liveness. Background tasks or subagents still running at a harness turn-end signal are live runtime truth, not durable work state. A producer that cannot certify a trustworthy terminal boundary must not settle at all (requirement 13 in the [requirements report](../../reports/2026-08-25-rozoro-derived-requirements.md)) rather than settle with a hedged verdict; the retry-identity rule below makes a premature settlement fail loudly when the true terminal result arrives;
- `--needs` is a bounded free-text value under the same 1,000-character normalization rule as `--message`, for the `inputs-needed` fact. Anything larger belongs in a ZR4 artifact referenced from the turn;
- verdict and needs join settlement identity: an idempotent retry must repeat them exactly, and a conflicting verdict fails deterministically with exit class 4, matching the existing outcome/summary retry rules;
- the mailbox event envelope carries `verdict` and `needs` when present, so `inbox unread` and `inbox pending` expose the routing fact directly. The invariant from the report holds: a watchtower never parses words like "blocked" out of prose;
- verdict vocabulary changes are contract changes. Adding a value is additive for JSON consumers but needs the compatibility review the [contracts index](../../architecture/contracts/README.md) requires, because watchtowers switch on it.

Tests: settle with and without verdict, retry equality including verdict/needs, conflicting-verdict rejection, envelope exposure in unread and pending, Scenario B end to end (`outcome=completed`, `verdict=blocked`), and needs-length bounds.

## ZR2: durable brief/source reference

The original request must survive session churn without recreating a growing handoff document.

```sh
zxro work create auth-fix --watchtower main --brief-stdin < brief.md
zxro work brief set auth-fix --stdin
zxro work brief path auth-fix
```

Decisions:

- the brief is stored through the artifact store with a work-scoped reference, `artifact:work:<work-id>:brief`. This extends the reference grammar with an owner scope; the reference stays opaque to callers and the durable-store contract's artifact section gains the work-scoped form. ZR4's storage generalization lands first so this reuses it;
- one brief per work item, set once. `work brief set` on a work item that already has a brief fails with exit class 4. The brief records original intent; corrections and later context belong in turn artifacts or the bounded work summary. This is the report's guard against rebuilding `handoff.md`;
- the immutable brief is also the measuring stick for ZR1 verdicts. When a producer cannot honestly classify `done`, `partial`, or `blocked` against the brief, the work has become different work: open a new work item with a new brief instead of amending the old one. Brief drift is expected, auditable, and a signal for improving brief writing outside zxro, not a defect to patch in place;
- setting a brief is allowed only while the work item is open. Payload bounds match other artifacts;
- `work show` returns the brief reference and byte count, never the body. `work brief path` is the deliberate retrieval step, with the same symlink/ownership/digest checks as `artifact path`;
- `--brief-stdin` at create time is a convenience for the common case; create-then-set has the same durable result. Create with brief must be atomic: a failed brief write must not leave a work record behind.

Tests: create with brief, set-once conflict, closed-work rejection, brief survives turns and close unchanged, bounded `work show`, path retrieval with digest verification, and atomicity of create-with-brief.

## Sequencing

```text
WP-A  ZR3 turn bind          no dependencies, contract already written
WP-B  ZR4 artifact put       generalizes artifact storage
WP-C  ZR1 verdict            independent; --needs pairs well with ZR4 refs
WP-D  ZR2 brief              depends on WP-B's work-scoped storage
        |
        v
Rozoro-shaped acceptance tests (Scenarios A-E as regression suite)
```

WP-A and WP-C can proceed in parallel. WP-D waits for WP-B. Each package is one PR with its contract-document updates included, per the [documentation update playbook](../../playbooks/documentation-update.md); the durable store contract, session binding contract, CLI spec, and conventions compatibility section are updated in the PR that changes the behavior, not afterward.

These packages slot between M1 and the M5/M6 harness integrations in the [implementation plan](./implementation-plan.md): Pi and Claude hooks should settle turns with verdicts from day one rather than retrofitting them.

## Acceptance

- [ ] Scenario B: a completed execution can report `verdict=blocked` and the watchtower routes on the field, not prose.
- [ ] Scenario C: many turns and large artifacts leave `inbox unread`, `work show`, `turn show` output sizes unchanged.
- [ ] Scenario D: late native-ID binding is idempotent, conflict-safe, and never changes work or turn identity.
- [ ] A work item's original brief is retrievable after settlement bursts, work close, and process restarts.
- [ ] Scenario A's 12-task burst passes with verdict-carrying events.
- [ ] All new fields round-trip through `--json` and older-binary downgrade behavior is documented.

## Human gate

Each work package edits published contracts (settlement identity, artifact grammar, turn binding), so each PR needs the compatibility review the contracts index requires. The verdict vocabulary in ZR1 is the one decision worth an explicit maintainer sign-off before implementation starts, since watchtower logic will switch on it.

## Related

- [Rozoro-derived requirements report](../../reports/2026-08-25-rozoro-derived-requirements.md)
- [Implementation plan](./implementation-plan.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [Session binding contract](../../architecture/contracts/session-binding.md)
- [v0.x CLI](../surfaces/cli.md)
- [Execution index](./README.md)
