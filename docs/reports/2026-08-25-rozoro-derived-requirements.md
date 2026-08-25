---
name: rozoro_derived_requirements
description: "Operational requirements and design constraints zxro should inherit from real Rozoro usage, without inheriting Rozoro's broader runtime and orchestration machinery."
type: report
tags: [reports, rozoro, zxro, architecture, requirements, planning]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-25"
sources:
  - ref: https://github.com/odjhey/rozoro/releases/tag/v0.0.2
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/tree/v0.0.2
    credibility: primary
  - ref: https://github.com/odjhey/zxro/tree/master
    credibility: primary
created_at: 2026-08-25T12:32:00+08:00
updated_at: 2026-08-25T12:46:00+08:00
---

# Requirements zxro inherits from Rozoro usage

## Why this document exists

Rozoro is useful to zxro as a source of production-shaped requirements.

The question for zxro is not:

> Which Rozoro components should zxro replace?

It is:

> What did we learn from using Rozoro for real parallel agent work, and which of those lessons belong in zxro's smaller durable coordination contract?

Rozoro grew around a wider responsibility set: task/session hosting, lifecycle observation, durable reports, notification delivery, runtime control, watchtower coordination, Herdr integration, and compatibility behavior. zxro deliberately has a narrower thesis.

That means the goal is not to reproduce Rozoro in another repository. The goal is to extract the requirements that survived real use and make those requirements native to zxro where they are provider-neutral durable coordination concerns.

Rozoro remains a useful reference workload and future integration consumer. It does not define zxro's implementation shape.

## Baseline

The Rozoro observations in this report use release `v0.0.2`, commit `18be2380ad8fc6baf2e56a2c3a28654a871916ab`.

The zxro baseline is `master` as of 2026-08-25, commit `a1dbf0a1ffbad78b370ded9edd1cf924917f2165`.

zxro M0/M1 already proves stable watchtower/work/turn identity, durable settlement, bounded artifact references, ordered mailbox delivery, independent read acknowledgement, per-event handled state, concurrency, and crash-gap repair through the public CLI.

The requirements below therefore split into three groups:

1. **already learned and already represented in zxro**;
2. **learned from Rozoro but still incomplete in zxro**;
3. **Rozoro machinery we should deliberately not inherit unless a zxro-specific failure proves the need.**

## Product stance

The durable core should remain small:

```text
watchtower / human / integrations
              |
             zxro
   durable work / turns / attention
              |
      replaceable providers

runtime/session execution remains outside:

watchtower / human
       |
 acpx / native adapter
       |
 Pi / Claude / other harness
```

The main test for a proposed zxro feature is:

> Is this durable, provider-neutral coordination state that remains useful when the runtime, harness, host, workflow, and repository all change?

If not, it probably belongs outside zxro.

# What Rozoro usage taught us

## 1. Logical work identity must survive session churn

Rozoro made it clear that a task is not a pane, process, cwd, native conversation ID, or one agent turn.

Real work may involve:

```text
auth-fix
  coder turn
  reviewer turn
  coder follow-up
  tester turn
```

The durable address must remain stable while the runtime session may be resumed, replaced, or abandoned.

### zxro requirement

Keep the current separation:

```text
work_id   logical work
turn_id   one delegated execution
runtime/session/native id   external execution identity
```

Do not derive a work ID from cwd, branch, process ID, pane ID, acpx session name, or provider-native conversation ID.

**Status:** already represented in zxro M0/M1 and the session-binding contract.

---

## 2. One work item may need several distinct crew roles

Rozoro usage is not well modeled as one task = one long-running worker conversation. A work item can move through coder, reviewer, tester, scout, or operator turns while remaining one logical piece of work.

### zxro requirement

Turns must stay first-class and independently inspectable. A work item owns a history of turns; a turn records the target cwd, agent/runtime address, terminal result, and artifact references.

Do not hard-code role names or workflow transitions into zxro. `coder -> reviewer -> tester` is a consumer workflow, not a durable-store state machine.

**Status:** already represented in zxro.

---

## 3. Execution outcome and work-routing verdict are different facts

This is the most important remaining semantic gap.

Rozoro handoffs distinguish work-facing states such as:

```text
done
waiting
needs-action
failed
blocked
```

and also carry structured information such as `reason`, `pending`, and `inputs-needed`.

zxro currently records execution outcomes:

```text
completed
failed
cancelled
```

plus a bounded free-text summary.

Those answer different questions.

A reviewer may execute successfully and report:

```text
execution: completed
work result: blocked
reason: operator decision required
```

Calling the execution `failed` would be false. Calling it only `completed` loses the routing fact.

### zxro requirement

Represent execution outcome separately from a small structured work-facing verdict.

A shape worth evaluating is:

```text
execution outcome: completed | failed | cancelled
result verdict:    done | waiting | needs-action | blocked
inputs-needed:     optional bounded value or reference
```

Exact names remain open. The invariant does not:

> The watchtower must not need to parse words such as `blocked` or `waiting` from prose to make a routing decision.

**Status:** gap. High priority.

---

## 4. The original work request must remain recoverable

Rozoro keeps a durable `brief.md`. That matters operationally: after many turns or a restart, the operator still needs to know what the logical work was originally about.

zxro's durable work identity should not depend on recovering that intent from a watchtower transcript or native model conversation.

### zxro requirement

A work record should preserve bounded source context and/or a durable reference to the original brief.

Prefer:

```text
work
  bounded source/current summary
  optional brief/source artifact reference
```

Do not recreate one growing `handoff.md` that combines initial intent with every later result.

**Status:** gap. High priority.

---

## 5. Runtime identity often becomes known after execution starts

Rozoro had to link durable task identity to native harness/session identity after launch. That is normal, not an edge case.

A caller may know:

```text
work_id
turn_id
runtime=acpx
agent=claude
session=coder-auth
cwd=/repo/worktree
```

before the underlying native conversation ID is exposed.

### zxro requirement

Support safe late enrichment of an existing turn binding.

The documented direction is appropriate:

```sh
zxro turn bind <turn-id> \
  --native-session-id <id> \
  --source acpx.agentSessionId
```

Binding updates must be idempotent. A conflicting native identity must fail closed rather than silently relink the turn.

**Status:** contract exists; public implementation is still missing on `master`. High priority.

---

## 6. Runtime resume and durable identity must stay separate

Rozoro's exact-resume work showed that storing an identifier is not the same as proving the runtime can resume the same conversation.

### zxro requirement

zxro stores durable identity and provenance. The runtime adapter decides whether exact resume is supported now.

Never silently turn:

```text
resume exact
```

into:

```text
start a new conversation
```

When a conversation is deliberately replaced, create a new turn instead of rewriting the old turn's binding.

**Status:** already represented in the session-binding and runtime-port contracts.

---

## 7. Read position, unresolved attention, and work acceptance are separate

Parallel Rozoro usage exposed the weakness of one monotonic acknowledgement cursor when many crews report around the same time.

At 8-12 concurrent tasks, the operator may want to read the entire burst, then handle the important items first without losing the lower-priority ones.

The durable distinctions are:

```text
event persisted
  != event observed
  != event handled
  != work closed / accepted
```

### zxro requirement

Keep the current zxro split:

```text
inbox unread   generation > read ack
inbox pending  actionable events not handled
ack            durable observation position
handle         independent event attention state
work close     logical acceptance/closure
```

A read ACK may advance past an unhandled event. That event must remain pending.

**Status:** already represented and tested in M1.

---

## 8. Attention identity must be task-scoped and independently handleable

Rozoro's generation model was useful for wake batching, but a delivery batch is not the durable identity of operator work.

zxro has an advantage because its current settlement events are already individually addressable.

### zxro requirement

Keep stable `event_id` separate from monotonic `generation`:

```text
event_id    stable handling identity
generation  delivery/read ordering
```

Do not introduce a separate attention-item object until one mailbox event can actually contain several independently actionable reasons. Avoid adding abstractions before the simpler event model fails.

**Status:** already represented in M1.

---

## 9. Routine reconciliation cost must not grow with task history

Rozoro accumulated append-only handoff prose and repeatedly re-read it during long-running review cycles. That turned durable history into repeated context cost.

The operational requirement is stronger than "support artifacts." It is:

> New attention should cost roughly the same to ingest on a fresh work item and on one with hundreds of historical turns.

### zxro requirement

Preserve progressive disclosure structurally:

```text
Level 0a  inbox unread
Level 0b  inbox pending
Level 1   work show
Level 2   turn show
Level 3   deliberate artifact resolution
```

Routine work, turn, inbox, status, and inspection reads must return bounded metadata and references rather than accumulated artifact bodies.

**Status:** already represented in zxro's contract; generic artifact support still needs expansion.

---

## 10. Evidence should be per-turn, not accumulated into one report

Real agent work produces different evidence types:

```text
review report
test log
diff or patch
screenshot
raw integration payload
CI result
PR/review reference
```

One append-only document is a poor storage model for all of them.

### zxro requirement

Generalize turn evidence behind independently addressable artifact or external references.

The provider-neutral model should support multiple artifacts/references per turn while keeping routine output bounded.

The M1 `--stdin` artifact proves the durability boundary but is not yet the full operator-facing capability.

**Status:** partial. Medium-high priority.

---

## 11. Durable result must exist before a wake is attempted

Rozoro's resident delivery work reinforced an asymmetric safety rule:

```text
lost wake        recoverable
lost result      not recoverable
```

### zxro requirement

Settlement ordering remains:

```text
persist artifacts
  -> commit terminal turn state
  -> publish matching durable mailbox event
  -> only then attempt disposable wake/notification delivery
```

A mailbox event must never point at missing terminal state or missing referenced artifact metadata.

A crash after terminal commit but before mailbox publication is allowed only if retry can converge on exactly one matching event.

**Status:** already represented and tested in M1.

---

## 12. Concurrency must be treated as the normal case

Rozoro is valuable specifically because several tasks can report together. A design that works only for one or two sequential workers is not enough.

### zxro requirement

Conformance and integration tests should continue to assume 10-12 near-simultaneous writers/readable events:

- no lost successful settlement;
- no duplicate logical settlement;
- no duplicate generation;
- deterministic conflicting retry failure;
- pending attention remains independently addressable after a burst;
- no global ordering assumption across unrelated watchtowers.

**Status:** core concurrency semantics already tested; the same scenario should become a required integration smoke for future live producers.

---

## 13. Startup, registration, and host idleness are not actionable completion

Rozoro v0.0.2's final release commit fixed a concrete Pi behavior where registration/startup could create a misleading `missing-report` wake.

That is an important lesson, but not a reason to import Rozoro's lifecycle reducer into zxro.

### zxro requirement

Keep actionability boring:

- registration is not completion;
- turn start is not completion;
- host process idleness is not semantic completion;
- diagnostic state change is not automatically attention;
- repeated identical terminal settlement is idempotent;
- only a trustworthy integration boundary should invoke `zxro turn settle` automatically.

If a harness cannot provide a trustworthy completion boundary, require manual settlement or fail closed rather than infer success from terminal state.

**Status:** design requirement for Pi/Claude/other integrations.

---

## 14. Live runtime truth and durable work truth must remain separate

Rozoro had to distinguish `idle`, `quiescent`, `done`, `blocked`, and operator acceptance. Collapsing them produces false state transitions.

### zxro requirement

zxro should answer durable questions:

```text
what work exists?
what turns exist?
what terminal results were committed?
what attention remains?
what artifacts/references exist?
```

The runtime answers live questions:

```text
is the session reachable?
is it working?
is it idle/quiescent?
can it resume?
can it be cancelled?
```

A higher-level client may join those views. zxro core should not manufacture one truth from the other.

**Status:** already represented in the runtime-port architecture.

---

## 15. Watchtower cwd and crew cwd are independent

Rozoro usage across repositories/worktrees showed that the coordinator's project context and the worker's target context are different configuration domains.

### zxro requirement

Keep both explicit:

```text
watchtower.cwd   orchestration project
turn.cwd         crew target
```

Never infer one from the other.

**Status:** already represented in zxro.

---

## 16. External actors eventually need the same durable work address

The same logical work may receive useful facts from outside an agent turn:

```text
GitHub review arrived
CI completed
background checker found a problem
human attached new information
```

Those facts should not require inventing a fake coding-agent turn.

### zxro requirement

When a concrete producer needs it, add a bounded typed external-event ingress that preserves zxro's existing event identity, ordering, durability, and attention semantics.

Keep the boundary explicit:

```text
external durable fact  -> zxro
model-visible message  -> acpx/runtime
```

Do not make zxro the chat/message transport merely because it owns the durable work address.

**Status:** future, demand-driven requirement. Medium priority after the core turn path is proven live.

---

## 17. Provider composition is useful; provider behavior is the contract

Rozoro's growth showed the cost of letting one storage/transport implementation become the architecture.

### zxro requirement

Keep work, turn, artifact, and mailbox behavior behind provider-neutral contracts. A future installation may compose providers, for example:

```text
work       Beads adapter
turns      zxro local provider
artifacts  local/object store adapter
mailbox    zxro local provider or compatible mail adapter
```

Public zxro semantics must remain stable across that composition.

The built-in provider is evidence that the contract works, not the permanent product schema.

**Status:** already represented in zxro's provider boundary.

# Requirements still worth implementing in zxro

The Rozoro-derived requirements above reduce to four near-term product gaps and two later ergonomics/integration items.

| ID | Requirement | Why Rozoro usage says it matters | Priority |
|---|---|---|---|
| `ZR1` | Structured routing verdict separate from execution outcome | successful execution may still produce blocked/waiting/needs-action work | high |
| `ZR2` | Durable original brief/source reference | logical work must remain understandable after session/history churn | high |
| `ZR3` | Late session/native-ID binding | provider-native conversation identity often appears after launch | high |
| `ZR4` | General multiple artifacts/external references per turn | real work produces review/test/diff/CI evidence, not one accumulated handoff | medium-high |
| `ZR5` | Typed external durable-event ingress | GitHub/CI/background/human facts need the same work address without fake turns | medium, demand-driven |
| `ZR6` | Bounded joined `inspect` view | operators need a cheap joined view without loading history/artifact bodies | medium |

`ZR1` through `ZR4` are the strongest candidates for immediate planning because they affect the semantic completeness of zxro as a durable work layer. `ZR5` and `ZR6` can follow without changing the core model.

# What zxro should not inherit from Rozoro

The most valuable extraction is often a boundary rather than code.

## Do not inherit the resident event-bus stack by default

Do not port these merely because Rozoro needed them:

- mandatory daemon;
- AF_UNIX socket protocol;
- resident server/client stack;
- SQLite/WAL lifecycle event store;
- producer spools;
- lifecycle reducer and projections;
- driver registration epochs;
- delivery offers and reconnect state;
- Herdr membership reconciliation;
- compatibility watcher modes.

Rozoro needed a resident semantic owner because it was interpreting multiple live runtime and host signals. zxro currently does not own that problem.

If zxro later has a concrete failure that requires a resident process, write a new decision from that evidence instead of treating Rozoro's implementation as inherited architecture.

## Do not inherit agent runtime execution

Keep these outside zxro core:

```text
start
send DATA
CONTROL interrupt/cancel/stop
runtime restart
exact resume execution
live session status
process hosting
```

The runtime port may define their semantics, but acpx/native adapters should execute them.

## Do not inherit orchestration policy

Keep these with the watchtower/operator/repository:

- business priority;
- decomposition;
- coder/reviewer/tester sequencing;
- model selection;
- profile/permission choice;
- worktree and branch policy;
- test/review/PR/CI/merge policy;
- final acceptance.

zxro records durable coordination facts. It should not decide what work happens next.

## Do not inherit terminal hosting

Panes, tabs, terminal buffers, reaping, tmux/Herdr behavior, and human interactive hosting are not durable work semantics.

A client may use them. zxro should not depend on them.

# Rozoro-shaped acceptance scenarios for zxro

Rather than plan a Rozoro migration first, use Rozoro's difficult operating cases as zxro acceptance tests.

## Scenario A: 12-task completion burst

Create 12 independent work items/turns owned by one watchtower and settle them near-simultaneously.

Required behavior:

- all successful writes survive;
- generations remain distinct and monotonic for that watchtower;
- the watchtower can read/ACK the full burst once;
- all 12 remain independently pending until handled;
- events can be handled in arbitrary business-priority order.

## Scenario B: successful reviewer reports a blocker

A reviewer process completes normally but reports that the logical work is blocked on an operator decision.

Required behavior after `ZR1`:

```text
execution outcome = completed
routing verdict   = blocked
```

No prose parsing is needed to discover the blocker.

## Scenario C: long-running work with large evidence

One work item accumulates many turns and large review/test artifacts.

Required behavior:

- one new unread event remains bounded;
- `work show`, `turn list`, `turn show`, and future `inspect` remain bounded;
- old artifact byte size does not increase routine reconciliation output;
- the operator resolves only the exact evidence needed.

## Scenario D: late native conversation identity

Create a turn before a native provider conversation ID is known. Bind the native ID later.

Required behavior after `ZR3`:

- binding does not change `work_id` or `turn_id`;
- identical rebinding is idempotent;
- conflicting native identity fails closed;
- stored identity remains data, not executable resume syntax.

## Scenario E: settlement crash gap

Interrupt a settlement after terminal turn commit and before mailbox publication.

Required behavior:

- no event is visible before durable terminal state exists;
- retry repairs the gap;
- exactly one logical event eventually becomes visible.

This is already covered by M1 and should remain a permanent conformance case.

## Scenario F: external CI/review fact

Once `ZR5` is justified by a real integration, attach a CI/review event to existing work without creating a fake agent execution.

Required behavior:

- durable event is attributable to the work and source;
- event remains bounded;
- read/handled semantics match other attention events;
- delivering the fact into an agent conversation remains a separate runtime action.

# How Rozoro should be used from here

Rozoro is a useful downstream validator for zxro, not the architectural center of this work.

As zxro closes `ZR1`-`ZR4`, we can optionally integrate Rozoro against the public zxro surface and ask:

- Can a real Rozoro workload use zxro work/turn identity without losing information?
- Can Rozoro stop relying on accumulated handoff parsing for durable attention?
- Can its native/runtime integration settle zxro turns at trustworthy completion boundaries?
- Can the watchtower process a 10-12 task burst through zxro pending/handle semantics?
- Can session recovery use zxro binding metadata without making zxro own resume execution?

That integration is validation evidence. It should not cause zxro to absorb Rozoro-specific runtime, hosting, profile, or orchestration concerns.

# Planning order

A reasonable work sequence is:

```text
ZR1 structured routing verdict
  +
ZR2 durable original brief/source
  +
ZR3 late session binding
  +
ZR4 generic artifacts/external references
        |
        v
Rozoro-shaped multi-turn / burst acceptance tests
        |
        v
live Pi/Claude integration validation
        |
        +--> ZR6 joined inspection ergonomics
        |
        +--> ZR5 external event ingress when demanded by a real producer
```

The key rule is to implement the durable requirement first, then use Rozoro as one demanding consumer of that contract.

# Decision summary

Apply these Rozoro lessons to zxro now:

- stable work identity independent from sessions and cwd;
- first-class turns for delegated executions;
- separate execution result from work-routing verdict;
- preserve original work intent durably;
- support late session binding;
- keep read ACK, pending attention, handling, and work acceptance independent;
- keep per-item event identity separate from delivery generation;
- keep routine context bounded regardless of accumulated history;
- store evidence per turn behind references;
- commit durable state before wake delivery;
- treat 10-12 concurrent completions as a normal operating case;
- trust native semantic completion, not startup/host idleness;
- keep runtime, orchestration, repository policy, and hosting outside zxro core;
- allow future external actors to address the same durable work without turning zxro into a chat transport;
- preserve provider-neutral behavior so optional stores can be composed later.

Do **not** treat Rozoro's daemon/event-bus/runtime machinery as a zxro backlog by default. The lesson from Rozoro is not that zxro needs every layer Rozoro built. The lesson is which durable invariants mattered after those layers were exercised in real parallel work.

## Related

- [What zxro should steal from Rozoro — and what it should leave behind](./2026-08-24-rozoro-lessons.md)
- [Product architecture](../architecture/product-architecture.md)
- [Durable store contract](../architecture/contracts/durable-store.md)
- [Session binding contract](../architecture/contracts/session-binding.md)
- [Agent runtime port](../architecture/contracts/agent-runtime-port.md)
- [v0.x implementation plan](../v0.x/execution/implementation-plan.md)
