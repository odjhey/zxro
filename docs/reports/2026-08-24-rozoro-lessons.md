---
name: rozoro_lessons_for_zxro
description: "Operational lessons from Rozoro that zxro should copy, adapt, or deliberately leave behind."
type: report
tags: [reports, rozoro, zxro, architecture, mailbox]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
sources:
  - ref: https://github.com/odjhey/rozoro/pull/46
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/pull/77
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/issues/8
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/issues/65
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/issues/66
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/issues/67
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/issues/80
    credibility: primary
created_at: 2026-08-24T16:03:00+08:00
updated_at: 2026-08-24T16:03:00+08:00
---

# What zxro should steal from Rozoro — and what it should leave behind

Rozoro is useful to zxro mostly because it failed in expensive ways. It started as a small task/session wrapper, then grew a resident event bus, lifecycle reducers, delivery ledgers, coalescing, compatibility modes, migration rules, and harness-specific adapters. Some of that was necessary for Rozoro. A lot of it is exactly what zxro is trying not to own.

The useful extraction is therefore not “port Rozoro core.” It is **port the invariants that survived contact with real use, while refusing the machinery that came from Rozoro’s wider scope**.

## The short version

zxro’s current direction is sound:

- stable work identity outside native agent sessions;
- separate watchtower and crew cwd values;
- CLI-first, dependency-free core;
- large evidence behind references instead of repeated prompt injection;
- acpx / native harnesses owning agent sessions;
- repository workflow, model choice, review policy, and merge policy above zxro.

One design problem is worth fixing before implementation: **a generation cursor is not enough to represent operator attention**.

The current v0.x docs define `ack` as the highest consumed generation and `inbox pending` as everything after that cursor. That works while updates are handled strictly in order. It breaks when a watchtower receives a burst from 8–12 tasks and the operator wants to work on the important ones first. Acknowledging a later generation can make earlier, still-unhandled work disappear from the normal pending view.

Rozoro reached the same wall. Its target mailbox design keeps delivery batches separate from independently handled task-scoped attention. zxro can take the smaller version of that idea without importing Rozoro’s event-bus stack: give each actionable inbox event a stable identity, keep the generation as ordering/read position, and track handled state per event.

## Copy now

| Rozoro lesson | zxro action | Why |
|---|---|---|
| Durable task/work identity must outlive a native session | **Keep** the current `work_id` / `turn_id` split | Resume, replacement, review, and follow-up should not change the logical address of work |
| Coordinator cwd and worker cwd are different things | **Keep** the explicit watchtower project cwd vs turn cwd model | Rozoro repeatedly had to reason about harness config and target worktrees separately |
| Routine reconciliation must be delta-sized | **Keep and test hard** | Rozoro issue #65 found a 56 KB handoff re-read roughly 20 times for one task: more than 1 MB of identical prose re-entered context |
| Durable state must exist before a wake or notification | **Keep** | Lost wake is recoverable; lost result is not |
| Native lifecycle evidence is semantic truth | **Adopt as an integration rule** | Host/process “idle” is not proof that a harness has finished meaningful work, especially with background/subagent activity |
| Delivery/reading is not task resolution or operator acceptance | **Adopt before M1** | This is the mailbox problem in smaller form; one cursor cannot represent out-of-order handling |
| Workflow and VCS policy belong above the substrate | **Keep out of zxro** | Rozoro issue #8 showed how a teardown guard accidentally became Git policy and could not attribute shared-checkout changes to one task |
| Prefer explicit recovery over clever inference | **Keep** native session recovery and fail-closed state checks | A durable, inspectable address beats guessing from process state or conversation prose |

## The mailbox lesson: borrow the invariant, not the schema

Rozoro’s target model eventually needed stable mailbox items because a notification generation could contain several tasks and the operator might handle only some of them. zxro does not need that whole schema in v0.x. Its settlement events are already task-scoped.

A smaller model is enough:

```text
inbox event
  event_id      stable handling identity
  generation    monotonic ordering / read position
  work_id
  turn_id
  outcome
  bounded summary
  artifact refs

read ack
  highest generation the watchtower has durably observed

handled state
  event_id -> handled_at
```

The important non-equivalence is:

```text
event persisted
  != event observed / read-acked
  != event handled
  != work accepted / closed
```

That gives the CLI two useful views:

```text
zxro inbox unread   # generation > read ack; cheap delta feed for context
zxro inbox pending  # actionable events not handled; may be processed out of order
zxro inbox handle <event-id>
zxro ack --through <generation>
```

`ack` can move forward without losing lower-priority work because `pending` is driven by handled state, not by the read cursor.

Do **not** add a second `mailbox_item` object yet. If zxro later coalesces many reasons into one delivery event, or one event can carry several independently actionable reasons, that is the point where a separate attention-item identity earns its keep.

A proposed decision is recorded in [0002: Separate inbox delivery position from attention handling](../decisions/0002-separate-delivery-from-attention.md).

## Keep actionability boring

Rozoro issue #80 is a warning against turning every state change into attention. Production generated repeated wakes from registration/progress, diagnostic projection churn, stale membership, and byte-identical effective state. Nothing was lost, but the operator was paged for changes that did not require action.

zxro has an advantage: the v0 contract currently publishes an inbox event only when a delegated turn settles. Preserve that bias.

If zxro later records more lifecycle facts, distinguish them from attention:

- registration is history, not a reason to wake;
- turn start is history, not a reason to wake;
- liveness diagnostics are history, not a reason to wake;
- a changed diagnostic field is not automatically a changed actionable state;
- repeated identical settlement must stay idempotent;
- a future projection layer must compare canonical semantic/actionable state, not raw mutable JSON.

This is one of the strongest reasons not to import Rozoro’s reducer/projection design before zxro actually needs it.

## Keep native lifecycle authority outside zxro

Rozoro’s event-bus work corrected an early assumption that host-level `idle` or a foreground stop meant the task was finished. Claude could stop the foreground turn while native background/subagent work was still active. The safer rule was: **the harness that owns the work reports its semantic lifecycle; hosting infrastructure only reports liveness**.

For zxro this should stay simple:

- Pi integration may call `zxro turn settle` from Pi’s semantic settled signal;
- Claude integration may call it only from the supported hook semantics that mean the delegated turn has reached the zxro settlement boundary;
- acpx/process exit is useful evidence, but not automatically settlement truth;
- zxro core does not normalize harness lifecycle itself.

If a harness cannot provide a trustworthy settlement boundary, fail closed or require manual settlement instead of guessing.

## Keep workflow and repository policy outside the core

Rozoro issue #8 is a clean boundary lesson. A teardown command inspected Git status, upstream state, and unpushed commits. That sounded protective, but the command did not own the checkout and could not attribute changes when several crews shared it. It also implicitly made Git the repository model.

zxro should continue to avoid:

- worktree creation or deletion;
- Git/Jujutsu status checks as core preconditions;
- PR, review, test, or merge policy;
- planner/coder/reviewer/tester as hard-coded workflow states;
- repository acceptance rules.

A watchtower, repository-local instructions, or a future work-graph layer can compose zxro primitives into those workflows.

## Scars worth remembering

### Re-reading durable prose becomes the token bill

Rozoro issue #65 measured the problem rather than merely predicting it: one 56 KB handoff was read around 20 times during a long review train. zxro’s current artifact-reference and progressive-disclosure design is the right response. Keep the invariant structural: old artifact byte size must not change routine reconciliation output.

### Background infrastructure creates cleanup obligations

Rozoro issue #66 found orphaned `rozorod.py` processes from interrupted tests, some many hours old. zxro avoids this entire class while it remains a foreground CLI with no daemon. If zxro ever adds a resident process, process ownership, interruption cleanup, and SIGKILL recovery become release gates, not test-harness polish.

### Teardown can destroy things the durable model never saw

Rozoro issue #67 captured a subtle operator race: a pane was force-reaped while a human had unsubmitted text in the terminal input buffer. The conversation could be resumed; the unsent text could not. zxro should not grow process/pane teardown merely because it knows a session address. Session hosting and interactive input ownership belong to the runtime/operator layer.

### Ordering and idempotency must be boring before integration

Rozoro issue #80 also exposed a producer sequence contract violation: one adapter began sequence numbers from wall-clock time while the reducer required contiguous values starting at 1. The result was durable events that never became valid current state.

zxro’s simpler file-backed design should still test the same class of invariant:

- concurrent settlements never duplicate generations;
- retry of one exact settlement is idempotent;
- conflicting retry fails;
- no timestamp is used as a uniqueness or ordering contract;
- state/result/artifact publication happens before the inbox event becomes visible.

## Do not copy yet

These Rozoro components solved problems created by Rozoro’s broader ownership. They are not zxro features unless a concrete zxro failure proves otherwise:

- resident daemon;
- AF_UNIX protocol and reconnecting clients;
- SQLite/WAL event store;
- producer spools;
- lifecycle reducer and projections;
- Herdr membership reconciliation;
- notification coalescer;
- driver registration epochs and delivery offers;
- schema migration/rollback machinery;
- harness-specific runtime adapters in core;
- process teardown/reaping;
- role/model/profile selection;
- legacy compatibility modes.

The best thing zxro can copy from Rozoro here is the restraint Rozoro arrived at in PR #77: use ACP/acpx and harness-native capabilities as far as they go, then own only the missing durable address/mailbox behavior.

## Suggested v0.x gates

Before M1 is considered stable, add black-box cases for these behaviors:

1. Settle events 1–10, read/ack through 10, handle only events 8 and 3, and prove every other event remains in `inbox pending`.
2. Prove `inbox unread` is empty after ack even while `inbox pending` still contains unhandled events.
3. Prove handling is idempotent and does not mutate or delete the immutable inbox event.
4. Prove work closure is independent from read ack and event handling.
5. Prove registration/start/liveness integration signals cannot create attention unless a later design explicitly promotes them.
6. Keep the existing large-artifact context-cost fixture.
7. If zxro ever adds a daemon or long-lived child, add interruption/SIGKILL cleanup tests before calling it supported.
8. If zxro ever adds projections, add no-op/actionable fingerprint and active-membership tests before using them to wake a watchtower.

## Recommendation

Do not port Rozoro’s implementation. zxro is valuable precisely because it can be the part Rozoro discovered underneath itself: **a small, durable work-address and attention layer that survives session churn without becoming the agent runtime, workflow engine, or repository supervisor**.

The one Rozoro lesson that belongs in zxro’s core model now is per-item attention state. Everything else should continue to earn its way in through a demonstrated failure of the CLI-first design.
