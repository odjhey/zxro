---
name: rozoro_replacement_assessment
description: "Assessment of which Rozoro v0.0.2 responsibilities zxro can replace, which gaps belong in zxro, and which responsibilities should stay with Rozoro or external runtimes."
type: report
tags: [reports, rozoro, zxro, architecture, migration, planning]
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
updated_at: 2026-08-25T12:32:00+08:00
---

# Rozoro replacement assessment

## Recommendation

Do not replace Rozoro wholesale with zxro.

The useful target is a smaller split:

```text
operator / watchtower
        |
      Rozoro
 opinionated orchestration + UX
        |
   +----+------------------+
   |                       |
  zxro                    acpx
 durable work         agent runtime/session
 turns/mailbox        start/send/control/resume
   |                       |
 durable provider      Pi / Claude / ...
```

Herdr can remain an optional human-facing host when pane inspection is useful. It is not part of the zxro contract.

This is consistent with both projects' current direction. Rozoro v0.0.2 already says ACP/acpx should be tested before more lower-level runtime machinery is extracted. zxro deliberately owns durable work identity, turns, settlement, bounded artifacts, and watchtower attention while leaving agent process hosting and session transport elsewhere.

The migration goal should therefore be:

- replace Rozoro's durable task/report/attention substrate with zxro where zxro already has the right abstraction;
- move runtime/session operations to acpx or native runtime adapters instead of porting them into zxro;
- keep Rozoro as the opinionated product layer for dispatch, composed status, profiles, operator UX, and optional hosting;
- delete Rozoro machinery that exists only because Rozoro currently owns lower-level lifecycle and delivery semantics, once the replacement path is proven.

This document is a planning anchor, not approval to remove the working Rozoro v0.0.2 path.

## Comparison baseline

The Rozoro side of this assessment is release `v0.0.2`, commit `18be2380ad8fc6baf2e56a2c3a28654a871916ab`.

The zxro side is `master` as of 2026-08-25, commit `a1dbf0a1ffbad78b370ded9edd1cf924917f2165`.

M0/M1 zxro work/turn/mailbox behavior is already on `master`. Native Pi and Claude settlement integrations and the automated watchtower loop are still separate follow-on work and must not be treated as shipped just because their contracts exist.

## Target ownership

The end state should be boring:

| Layer | Owns |
|---|---|
| Rozoro / watchtower | dispatch, priority, role choice, composed operator UX, launch profiles, whole-stack preflight, optional wake integration |
| zxro | stable watchtower/work/turn identity, durable settlement, bounded artifacts, inbox delivery position, per-event attention handling |
| acpx / runtime adapter | start, send, control, stop, exact resume, live runtime/session status |
| Pi / Claude / other harness | native execution behavior and trustworthy lifecycle/completion semantics |
| Herdr or another host | optional panes, tabs, process hosting, human inspection |
| target repository | worktree, branch, tests, review, PR, CI, merge and acceptance policy |

The important rule is that a responsibility should move to zxro only when it is durable provider-neutral coordination state. Runtime actuation and workflow policy do not meet that test.

## Component replacement matrix

| Rozoro v0.0.2 concern | Replacement | Readiness | Disposition |
|---|---|---|---|
| durable task key / task identity | `zxro work` | available on `master` | replace |
| one delegated execution identity | `zxro turn` | available on `master` | replace |
| append-only `handoff.md` as accumulated report history | per-turn settlement summary + artifact references | basic M1 path available; richer artifacts still needed | replace, do not recreate the append-only aggregate |
| handoff acknowledgement cursor | `zxro inbox handle <event-id>` for attention; `zxro ack` for observed delivery | available on `master` | replace with split semantics |
| generation-centric reconcile ledger | `inbox unread` + read ACK + `inbox pending` + per-event handled state | available on `master` | replace |
| task attribution inside wake delivery | immutable mailbox event carrying `work_id` and `turn_id` | available on `master` | replace |
| durable result payload | zxro artifact reference | basic M1 `--stdin` artifact available | replace incrementally |
| `session.json` / task-to-conversation linkage | zxro turn runtime/session/native-session binding | partial | replace after late binding exists |
| `rzr-link` | `zxro turn bind` contract | documented, not on `master` | zxro gap |
| `rzr-start` / `rzr-spawn` | zxro creates durable work/turn; acpx starts runtime | split across zxro + acpx | do not copy all-in-one start into zxro |
| `rzr-send` | acpx/runtime DATA plane | external | keep out of zxro |
| `rzr-control` | acpx/runtime CONTROL plane | external | keep out of zxro |
| `rzr-resume` | zxro stores identity; runtime performs exact resume | partial metadata path | keep execution out of zxro |
| `rzr-status` | compose zxro durable truth + runtime live truth | no single joined command today | likely Rozoro UX over two sources |
| `rzr-list` | zxro work/turn list + runtime session list when needed | partial | compose rather than duplicate |
| `rozorod` resident daemon | no direct zxro replacement | intentionally absent | delete when no longer needed; do not port by default |
| Unix socket/server/client protocol | no direct zxro replacement | intentionally absent | delete when no longer needed; do not port by default |
| SQLite lifecycle event log | zxro terminal settlement/mailbox event model for durable coordination | different scope | do not reproduce full lifecycle log in zxro without a demonstrated need |
| lifecycle reducer and session/task projections | native settlement integrations + runtime status | different scope | prefer deletion over porting |
| Pi/Claude lifecycle adapters | thin integration invoking public `zxro turn settle` at a trustworthy completion boundary | follow-on integration work | integration, not zxro core |
| watchtower wake/coalescing | wake integration after durable zxro settlement | not zxro core | keep outside durable store |
| Herdr membership/reconciliation | Herdr/runtime hosting | external | keep out of zxro |
| pane teardown/reaping | runtime/host/operator | external | keep out of zxro |
| crew profile/model/effort/permissions | Rozoro/watchtower/harness config | external to zxro | keep Rozoro-specific |
| task prompt/brief rendering | Rozoro/watchtower | external to zxro | keep rendering out of zxro; preserve source brief separately |
| whole-stack `doctor` | Rozoro composed preflight | external to zxro | keep Rozoro-specific |
| priority, decomposition, coder/reviewer/tester loops | watchtower/operator | external to zxro | keep out of core |

## zxro gaps worth closing

The current M0/M1 loop is enough to prove durable work and attention semantics, but it is not yet a complete replacement for the durable parts Rozoro relies on in real operation.

### G1. Separate execution outcome from routing verdict

**Owner: zxro core. Priority: high.**

Rozoro handoffs distinguish work-facing states such as:

```text
done
waiting
needs-action
failed
blocked
```

and carry structured fields such as `reason`, `pending`, and `inputs-needed`.

zxro currently has terminal execution outcomes:

```text
completed
failed
cancelled
```

plus a bounded free-text summary.

Those are not the same concept. A reviewer can execute successfully and report that the work is blocked on an operator decision. Calling that turn `failed` is wrong; calling it merely `completed` loses the routing fact.

Do not make the watchtower parse words such as `blocked` from prose. Add a small provider-neutral structured result dimension. A reasonable shape to evaluate is:

```text
execution outcome: completed | failed | cancelled
result verdict:    done | waiting | needs-action | blocked
inputs-needed:     optional bounded field or reference
```

Exact names are open. The invariant is not: runtime execution outcome and work-routing verdict are separate facts.

### G2. Preserve the initial work brief without reviving `handoff.md`

**Owner: zxro core. Priority: high.**

If `work_id` is the durable address of logical work, an operator should be able to recover what that work was originally about without searching the watchtower transcript.

Add bounded work context and/or an explicit brief artifact reference. Do not use one growing document for both the original brief and all later handoffs.

The preferred shape is roughly:

```text
work
  bounded current/source summary
  optional brief/source artifact reference
```

Historical turn results remain separate per-turn objects and artifacts.

### G3. Implement late session binding

**Owner: zxro core. Priority: high.**

The session-binding contract already documents the right behavior: runtime or provider-native conversation identity may only become known after the turn starts.

The public CLI needs the intended enrichment operation, for example:

```sh
zxro turn bind <turn-id> \
  --native-session-id <id> \
  --source acpx.agentSessionId
```

This is the clean replacement for Rozoro's durable session-linking responsibility. It must be idempotent and fail closed on conflicting identity.

Until this exists, Rozoro's `rzr-link` / session-link flow cannot be removed cleanly.

### G4. Generalize turn artifacts and external references

**Owner: zxro core/provider contract. Priority: medium-high.**

M1 proves the artifact boundary with settlement stdin, but real work needs several independently addressable pieces of evidence:

```text
review report
test log
diff or patch
screenshot
raw hook payload
CI result URL
PR/review URL
external durable artifact
```

Keep routine reads bounded. Add generic artifact attachment/reference semantics rather than returning to accumulated handoff prose.

### G5. Add typed external durable-event ingress when a real producer needs it

**Owner: zxro core contract, later milestone. Priority: medium.**

A durable work address will eventually receive facts from actors that are not crew turns:

```text
GitHub review arrived
CI completed
background checker found a problem
human attached new information
```

Do not manufacture fake turns just to place these facts in the watchtower inbox.

When needed, add a bounded typed external event ingress with the same durability, ordering, identity, and attention rules as the existing mailbox. Keep model-visible delivery separate:

```text
external durable event -> zxro
model-visible message   -> acpx/runtime
```

This should be demand-driven. The initial cutover does not need to solve every future event type.

### G6. Add a bounded joined inspection view

**Owner: zxro M2/operator ergonomics. Priority: medium.**

Rozoro can compose current public zxro commands during migration, but daily operation is easier with one read-only bounded view of:

```text
work
latest/relevant turns
pending attention
artifact references
session binding
```

The documented `inspect` direction is appropriate. It must not repair, ack, handle, resume, or inline artifact bodies as a side effect.

## Things zxro should refuse to absorb

These features are tempting because Rozoro already has code for them. Most would make zxro worse.

### Runtime/session execution

Do not add core wrappers merely to make zxro own:

- agent start;
- DATA send;
- CONTROL actions;
- process stop/restart;
- exact runtime resume;
- live runtime status.

The runtime port already defines the semantics. acpx or a native adapter should execute them.

### General lifecycle reduction

Do not port Rozoro's resident event bus, full lifecycle event log, reducer, task projections, registration epochs, producer spools, or host membership reconciliation into zxro by default.

Rozoro needed those because it was trying to derive durable semantic state from several live harness/host sources. zxro's smaller contract should accept trustworthy terminal settlement at the integration boundary and leave live runtime truth with the runtime.

If a future zxro requirement cannot be solved without a resident lifecycle owner, write a new decision from that failure. Do not assume the Rozoro implementation is the default inheritance path.

### Orchestration and repository policy

Keep these above zxro:

- priority and routing;
- task decomposition;
- role selection;
- coder/reviewer/tester loops;
- model/profile selection;
- worktree and branch policy;
- PR, test, CI and merge rules;
- operator acceptance.

zxro records durable coordination facts. It does not decide what work should happen next.

### Hosting and interactive terminal ownership

Do not make zxro responsible for panes, tabs, terminal buffers, reaping, or interactive teardown. Herdr or another host may continue to provide this when humans need it.

## Why deleting machinery is better than porting it

Rozoro v0.0.2's final release commit fixed a concrete Pi projection problem: registration and a newly started busy turn could be interpreted as `missing-report` and wake the watchtower before meaningful work had finished.

That fix is useful evidence, but not evidence that zxro needs the same projection stack. It is evidence that once the durable layer owns live lifecycle interpretation, it inherits a large semantic surface.

zxro should take the invariant instead:

> A trustworthy harness completion boundary may settle a turn. Startup, registration, host idleness, and diagnostic state changes do not become attention merely because they changed.

## Proposed cutover sequence

### Phase 0 — close the durable replacement gaps

Before making zxro authoritative for Rozoro tasks, plan and implement at least:

1. G1 structured routing verdict separate from execution outcome;
2. G2 durable source brief/reference;
3. G3 late session binding;
4. enough of G4 to preserve real review/test/report evidence without `handoff.md`.

G6 is useful but can be supplied temporarily by Rozoro composition. G5 can wait until a non-turn producer actually needs durable ingress.

### Phase 1 — shadow write from Rozoro into zxro

Keep Rozoro v0.0.2 behavior authoritative.

For each real Rozoro task:

```text
Rozoro task create
  -> zxro work create

Rozoro crew execution
  -> zxro turn create

trustworthy terminal result
  -> zxro turn settle
```

Attach the same session identity and result evidence to both systems where possible. Do not drive watchtower decisions from zxro yet.

Evaluate this with the expected fleet size, especially bursts around 10–12 simultaneous tasks.

Evidence required:

- no lost or duplicate settlements;
- correct work/turn attribution;
- pending attention remains after read ACK until independently handled;
- structured blocked/needs-action/waiting results survive without prose parsing;
- result evidence remains accessible without loading accumulated history;
- native session recovery metadata agrees with the actual runtime.

### Phase 2 — make zxro authoritative for durable work and attention

Once the shadow path is boring, switch Rozoro's durable reads to zxro for:

- logical work identity;
- turn history;
- terminal results;
- artifact references;
- unread delivery;
- pending attention;
- handled state;
- work closure/acceptance state where appropriate.

At this point stop treating these as authoritative:

- accumulated `handoff.md` parsing;
- `.acked-blocks*` as the primary work-attention cursor;
- Rozoro generation ACK as the primary unresolved-attention model.

Keep compatibility reads only as long as migration requires them.

### Phase 3 — move runtime operations behind acpx/native adapters

Refactor Rozoro start/send/control/resume paths so the durable half and runtime half are visibly separate:

```text
Rozoro start
  -> zxro work/turn creation
  -> acpx start
  -> zxro turn bind when identity becomes known
```

and:

```text
Rozoro send/control/resume
  -> acpx/runtime operation using the zxro-recorded binding
```

Rozoro may keep these as convenience commands. The important change is ownership underneath them.

### Phase 4 — retire resident lifecycle machinery only after live proof

Candidates for deletion or legacy-only status include:

```text
rozorod
monitor socket/server/client protocol
SQLite runtime event store
lifecycle reducer/projections
producer spools
delivery-generation machinery that zxro has replaced
Herdr membership reconciliation used only for semantic completion
legacy handoff/open-item parsers and cursors
```

Do not remove them merely because the architecture looks cleaner. Remove them after the new path survives normal use, crashes, duplicate completion signals, session replacement, and bursty parallel work.

### Phase 5 — leave Rozoro intentionally small

The surviving Rozoro product can still be valuable:

```text
rozoro start/status/list
crew/profile selection
doctor/preflight
watchtower wake and dispatch integration
composed durable + runtime status
migration/compatibility commands
optional Herdr UX
```

That is a product layer, not a second durable work store or a second agent runtime.

## Candidate work packages

These are planning buckets, not implementation authorization.

| ID | Work package | Owner | Blocks cutover? |
|---|---|---|---|
| RZ-G1 | structured work-routing verdict on turn settlement | zxro core | yes |
| RZ-G2 | durable work brief/source reference | zxro core | yes |
| RZ-G3 | late `turn bind` session enrichment | zxro core | yes |
| RZ-G4 | generic multi-artifact/reference support | zxro core/provider | yes for full handoff removal |
| RZ-G5 | typed external mailbox event ingress | zxro core/provider | no, demand-driven |
| RZ-G6 | bounded joined `inspect` view | zxro CLI | no |
| RZ-I1 | Pi native settlement integration | zxro integration | yes for Pi live cutover |
| RZ-I2 | Claude native settlement integration | zxro integration | yes for Claude live cutover |
| RZ-I3 | live acpx start/send/control/resume adapter validation | runtime integration | yes for runtime cutover |
| RZ-C1 | Rozoro shadow writer to zxro | Rozoro integration | phase 1 |
| RZ-C2 | Rozoro durable read/attention cutover to zxro | Rozoro integration | phase 2 |
| RZ-C3 | Rozoro runtime commands over acpx + zxro binding | Rozoro integration | phase 3 |
| RZ-C4 | legacy/event-bus retirement plan and compatibility window | Rozoro | phase 4 |

Each package should become a separate issue or task card once its contract and acceptance evidence are agreed. Avoid one migration mega-PR.

## Cutover gates

Do not declare a component replaced merely because zxro has a similarly named command.

A cutover is ready only when:

1. the replacement owner is unambiguous;
2. the public contract covers the Rozoro behavior that callers actually rely on;
3. crash/retry and duplicate-signal behavior is tested;
4. runtime identity and durable identity remain separate;
5. unresolved attention cannot disappear because delivery was acknowledged;
6. full evidence stays behind deliberate references rather than routine reconciliation output;
7. the replacement survives realistic multi-task bursts;
8. recovery and rollback to the known Rozoro path are documented for the migration window.

## Immediate planning recommendation

Start with RZ-G1 through RZ-G4 as zxro gap-design tasks. In parallel, continue the existing Pi/Claude integration work and prepare RZ-C1 as a Rozoro-side shadow adapter.

Do not start by deleting `rozorod` or rewriting Rozoro around zxro. The fastest way to learn whether the split is correct is to make zxro observe the same real work first, then move authority one boundary at a time.

## Related

- [What zxro should steal from Rozoro — and what it should leave behind](./2026-08-24-rozoro-lessons.md)
- [Product architecture](../architecture/product-architecture.md)
- [Durable store contract](../architecture/contracts/durable-store.md)
- [Session binding](../architecture/contracts/session-binding.md)
- [Agent runtime port](../architecture/contracts/agent-runtime-port.md)
- [v0.x implementation plan](../v0.x/execution/implementation-plan.md)
