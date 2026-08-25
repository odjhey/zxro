---
name: durable_store_contract
description: "Provider-neutral contract for zxro watchtower, work, turn, artifact, mailbox delivery, attention handling, concurrency, and crash-recovery behavior."
type: contract
tags: [architecture, contracts, durability, storage, mailbox]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T16:23:00+08:00
updated_at: 2026-08-25T19:15:39+08:00
---

# Durable store contract

## Purpose

zxro depends on durable behavior, not a particular storage engine. This contract defines the behavior required from storage providers so the first implementation can use local files while later adapters may use Beads, a local mail CLI, SQLite, or another system without changing the zxro CLI or agent integrations.

The contract has two goals:

- let zxro implementation proceed now against a stable behavior boundary;
- let candidate off-the-shelf tools be evaluated by conformance instead of by similarity to zxro's first implementation.

The built-in v0 provider may use indexed JSON, filesystem locks, and per-turn files. Those are implementation choices, not this contract.

## Owners and consumers

zxro owns the contract and translates CLI operations into provider calls.

Consumers include:

- the zxro CLI;
- watchtowers reading new delivery and unresolved attention;
- Pi and Claude completion integrations;
- operators inspecting or repairing local state;
- future storage adapters.

A provider does not need to understand Pi, Claude, ACP, acpx, worktrees, or agent reasoning.

## Capability split

A zxro installation may satisfy this contract with one provider or compose several providers.

```text
zxro CLI
   |
   +-- registry/work provider
   +-- turn provider
   +-- artifact provider
   +-- mailbox provider
```

The useful capability groups are:

| Capability | Responsibility |
|---|---|
| Registry | Watchtower identity and orchestration-project metadata |
| Work store | Stable logical work identity and current state |
| Turn store | One delegated execution, lifecycle, result summary, and references |
| Artifact store | Potentially large evidence addressed by opaque reference |
| Mailbox store | Immutable ordered events, read position, and independent per-event handled state |

A candidate may implement only one group. For example, Beads may satisfy the work-store contract while zxro keeps turns locally and another CLI provides mailbox semantics.

Provider composition must not change public zxro command behavior. Core code injects the M1 settlement, mailbox, and artifact capabilities defined in `zxro.contract`; CLI handlers do not construct a built-in M1 provider directly. Provider conformance fixtures target those capabilities and can be reused with provider-specific setup and fault hooks.

## Canonical objects

### Watchtower

A watchtower is a stable coordinator identity.

Minimum logical shape:

```json
{
  "id": "main",
  "cwd": "/Users/example/watchtowers/main"
}
```

Optional runtime addressing may include an agent name and session reference:

```json
{
  "agent": "pi",
  "session": "watchtower"
}
```

The cwd is the watchtower's orchestration project. It is not a default crew target.

### Work

Work is a durable logical job that survives several delegated turns.

```json
{
  "id": "auth-fix",
  "watchtower_id": "main",
  "state": "open",
  "summary": "Refresh-token handling needs correction."
}
```

Required properties:

- `id` is stable and independent from cwd, process IDs, branches, and provider session IDs;
- one watchtower owns the work at a time in v0.x;
- closing work does not delete its turns, artifacts, or mailbox history;
- current-state reads do not require replaying all historical bodies.

Dependencies, labels, priorities, parent/child links, claims, and semantic search are optional provider capabilities.

### Turn

A turn is one delegated execution against a work item.

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "work_id": "auth-fix",
  "watchtower_id": "main",
  "agent": "claude",
  "session": "coder-auth",
  "cwd": "/Users/example/src/app-wt/auth",
  "state": "running"
}
```

A settled turn adds a terminal execution outcome, bounded summary, optional producer verdict, optional needs text, and zero or more artifact references:

```json
{
  "state": "settled",
  "outcome": "completed",
  "summary": "Implemented refresh handling; operator approval remains.",
  "verdict": "blocked",
  "needs": "operator approval",
  "artifact_refs": [
    "artifact:550e8400-e29b-41d4-a716-446655440000:report"
  ]
}
```

Work, turn, and native session identity are separate concepts. Several turns may use the same persistent agent session, and one work item may involve several sessions.

### Artifact

An artifact is potentially large evidence that routine reconciliation must not inline.

Examples include reports, review findings, test logs, diffs, screenshots, raw hook payloads, and transcript exports.

Minimum metadata:

```json
{
  "ref": "artifact:550e8400-e29b-41d4-a716-446655440000:review",
  "kind": "review",
  "bytes": 18432
}
```

A provider may store artifact bytes itself or resolve the reference to another durable location. The reference is opaque to callers.

### Mailbox event

A mailbox event is immutable, bounded routing context for one watchtower.

```json
{
  "event_id": "evt-7a63...",
  "generation": 42,
  "type": "turn_settled",
  "watchtower_id": "main",
  "work_id": "auth-fix",
  "turn_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent": "claude",
  "outcome": "completed",
  "summary": "Implementation complete; operator approval remains.",
  "verdict": "blocked",
  "needs": "operator approval",
  "artifact_refs": [
    "artifact:550e8400-e29b-41d4-a716-446655440000:report"
  ],
  "created_at": "2026-08-24T16:31:00+08:00"
}
```

`event_id` is stable identity for attention handling. `generation` is monotonic delivery order and read position within one watchtower mailbox.

Global ordering across independent watchtowers is not required.

### Read acknowledgement

Each watchtower has one monotonic read cursor:

```json
{
  "watchtower_id": "main",
  "through_generation": 42
}
```

The cursor means "the watchtower has durably observed delivery through generation 42." It does not mean all attention through generation 42 is resolved.

### Handled state

Actionable events have independent handled state keyed by `event_id`:

```json
{
  "event_id": "evt-7a63...",
  "watchtower_id": "main",
  "handled_at": "2026-08-24T16:31:00+08:00"
}
```

Handled state does not mutate or delete the immutable event. It does not close the owning work item.

## Work-store operations

A compatible work provider must support the semantic equivalent of these operations.

### Create

```text
work.create(id, watchtower_id, metadata?) -> work
```

Requirements:

- create exactly one work identity;
- reject a duplicate ID rather than silently overwrite it;
- reject an unknown watchtower when registry validation belongs to the same provider boundary;
- after success, the record survives caller exit.

### Get

```text
work.get(id) -> work
```

The result is current state, not accumulated history. Output must remain bounded independently of historical artifact size.

### List

At minimum:

```text
work.list()
work.list(watchtower_id=...)
work.list(state=...)
```

Provider-native query syntax may differ. The adapter presents zxro semantics.

### Update

```text
work.update(id, changes) -> work
```

Conflicting or invalid updates must fail deterministically. The provider does not need generic JSON patch support.

### Close

```text
work.close(id) -> work
```

Close changes current state but preserves durable history. It is independent from mailbox read and handled state.

## Turn-store operations

### Create

```text
turn.create(work_id, agent, session, cwd, native_session_id?) -> turn
```

The operation must:

1. verify the work item exists and is open;
2. reject a new turn for closed work without creating a turn record;
3. resolve and persist the owning `watchtower_id`;
4. generate or accept a unique turn ID;
5. persist the running turn before returning success.

### Get

```text
turn.get(id) -> turn
```

The result contains metadata, current lifecycle state, bounded summary, and artifact references. It must not inline raw artifacts or transcripts.

### List

At minimum:

```text
turn.list(work_id=...)
turn.list(state=...)
```

### Settle

```text
turn.settle(id, outcome, summary, payload, source, verdict?, needs?) -> turn
```

Supported v0.x outcomes are:

```text
completed
failed
cancelled
```

Settlement is idempotent. Repeating the same outcome, normalized summary, optional verdict, and optional normalized needs returns the existing result and must not create another mailbox event. Retry payload may be omitted; when supplied, its digest must match the first settlement, and a settlement without payload cannot gain one later. A changed verdict or needs is a conflicting terminal settlement and fails with exit class 4 without mutation.

Verdicts use `done | partial | blocked`. They are producer claims about work against the brief or summary, not execution outcomes. `blocked` requires non-empty needs. Needs is invalid with `done`, `partial`, or an omitted verdict, is NFC-normalized, and is limited to 1,000 characters. An omitted verdict persists neither field. A verdict does not close work, handle an event, report runtime liveness, or assign an actor.

The event ID is allocated before terminal commit and stored with the settlement as its stable delivery identity. Adapters may map this identity to a provider-native idempotency mechanism or emulate it. Crash-gap publication must reuse the committed event ID.

## Artifact-store operations

A compatible artifact provider must support the semantic equivalent of:

```text
artifact.put(turn_id, kind, content-or-source) -> artifact_ref
artifact.stat(ref) -> metadata
artifact.resolve(ref) -> deliberate read target
```

`artifact.resolve` may return a local path, a provider handle, or another explicit retrieval target. It must never cause routine work, turn, inbox, or inspection reads to inline the artifact body.

Artifact references must not permit traversal outside the active provider namespace.

## Mailbox-store operations

Mailbox delivery and mailbox attention are separate concerns.

### Publish

```text
mail.publish(watchtower_id, event, idempotency_key) -> event
```

The mailbox assigns or exposes:

- one stable `event_id`;
- one monotonically increasing `generation` for that watchtower.

Publishing the same `idempotency_key` again must return the existing logical event rather than append a duplicate generation.

A new actionable settlement event begins unhandled.

A provider with message IDs, thread IDs, sequence numbers, or another native model may use those internally. The adapter must still present zxro event identity and generation behavior.

### Unread

```text
mail.unread(watchtower_id) -> events
```

`unread` is the delivery delta. It returns events whose generation is strictly greater than the watchtower's durable read cursor. Before returning an event, the provider must resolve its direct event-ID lookup and require exact event identity, owner, and generation agreement. Generation values are integers, not booleans or numeric strings.

If read ack is `40` and generations `41`, `42`, and `43` exist, `unread` returns only `41..43`.

Unread is the cheapest way to ingest what changed since the last observation.

### Pending

```text
mail.pending(watchtower_id) -> events
```

`pending` is the attention view. It returns actionable events that have not been handled, regardless of whether their generation is below or above the read cursor.

This allows a watchtower to acknowledge reading a burst, then handle events in business-priority order without hiding lower-generation work.

A provider may support filters or ordering such as work ID, age, or priority, but those are optional in v0.x.

### Ack

```text
mail.ack(watchtower_id, through_generation) -> ack
```

Rules:

- ack means "durably observed through generation N";
- ack may advance only to an existing generation;
- ack may not move backwards;
- repeating the current ack is allowed;
- ack never deletes inbox history;
- ack does not mark any event handled;
- the requested generation must be an integer, not a boolean, numeric string, or float, and validation occurs before provider state access;
- before advancing, ack must resolve and validate every newly acknowledged generation; a missing or mismatched generation fails closed without changing the cursor.

### Handle

```text
mail.handle(watchtower_id, event_id) -> handled_state
```

Rules:

- handling affects exactly one event;
- events may be handled out of generation order;
- handling first commits authoritative handled state, then removes unresolved attention;
- interruption around either write leaves the event pending or durably handled, and retry converges idempotently;
- handling the same event twice is idempotent;
- handling does not mutate the immutable event;
- handling does not close work;
- an unknown event ID fails without changing other attention state.

### History and diagnostics

An optional provider operation may expose:

```text
mail.since(watchtower_id, generation) -> events
```

for diagnostics and recovery.

A provider with only per-message acknowledgement may still conform if its adapter can separately represent zxro's read cursor and handled state. If the provider conflates "read" and "done" with no safe adapter path, it does not satisfy the mailbox contract.

## Settlement commit protocol

Provider composition must not require a distributed transaction.

zxro settles a turn in this order:

```text
1. persist referenced artifacts
2. commit terminal turn state with its allocated event ID
3. create the immutable generation event without overwriting
4. create the direct event-ID index without overwriting
5. advance mailbox high-water and unresolved state
6. return success
```

Steps 3 through 5 form a resumable publication state machine. Before mutating the requested turn or assigning a generation, settlement must resolve and validate the direct index of the mailbox's already-published boundary events at generations `highest` and `highest - 1`; a missing or mismatched boundary index fails closed without touching the requested turn or mailbox. Retry or another settlement then reconciles and validates an immutable event at `highest + 1` before proceeding. A committed direct index above high-water must advance mailbox state before success. Interruption before or after any publication write must not overwrite an event or lose visibility. If handling succeeds between index and mailbox commits, repair must preserve handled state and must not add the event to unresolved attention.

The safety rule is asymmetric:

> A watchtower must never receive a settlement event whose durable turn result and referenced artifact metadata cannot be resolved and matched to the event.

`unread` and `pending` must fail closed with exit class 5 if an event's terminal turn, ownership, settlement identity, outcome, summary, verdict, needs, or artifact metadata is missing or disagrees. They must not return a partially validated envelope.

A process may crash after step 2 and before step 3. That leaves a settled turn whose mailbox event has not yet been published. This state is recoverable. Retrying settlement or reconciliation must detect the committed settlement and idempotently publish the missing event.

A process must not report successful settlement to its caller until mailbox publication is durable.

Acceptable crash states are:

```text
running turn, no event
```

or:

```text
settled turn, event not yet published
```

or:

```text
settled turn, matching unhandled event published
```

This state is forbidden:

```text
settlement event published, referenced turn result missing
```

Adapters for separate work/turn/mail providers must preserve this ordering and idempotency behavior.

## Progressive-disclosure contract

Progressive disclosure is a storage contract, not a UI convention.

Routine consumers have two shallow mailbox views before drilling into evidence:

```text
Level 0a  inbox unread
          new bounded delivery since read ack

Level 0b  inbox pending
          bounded unresolved attention, including already-read events

Level 1   work get/show
          current work state and bounded summary

Level 2   turn get/show
          one execution and artifact references

Level 3   artifact resolve
          full evidence, fetched only when needed
```

The following reads must not inline artifact bodies:

- inbox unread;
- inbox pending;
- work show/list;
- turn show/list;
- routine inspect/status views.

v0.x bounds routing summaries at 1,000 Unicode characters after normalization. Providers may store larger bodies, but adapters must return bounded summaries and references for routine reads.

### Bounded context invariants

For a work item with hundreds of prior turns and large historical artifacts, one new unread event must cost roughly the same to ingest as one new event on a fresh work item.

```text
unread cost ~= new delivery
```

`pending` may grow with the number of genuinely unresolved actionable events. It must not grow with the byte size of their reports, logs, or transcripts. If authoritative handled markers remain after an interrupted handle, a pending read compacts those stale unresolved IDs so later empty reads return to fixed cost without exact-handle retries.

```text
pending cost ~= unresolved bounded events
```

not:

```text
pending cost ~= accumulated artifact history
```

Increasing the byte size of an old artifact must not increase the output size of `unread` or `pending` when the event envelopes are unchanged.

Providers must also bound reconciliation work by the requested view. `unread` reads generations after the watchtower's ack, `pending` reads unresolved events, and direct handling resolves one event ID. Empty views and one new settlement must not scan handled history or another watchtower's history.

## Isolation contract

The active zxro home is one logical durable-state and trust boundary.

Providers must support independent namespaces equivalent to separate `$ZXRO_HOME` values. Two homes may both contain `watchtower_id=main` and `work_id=auth-fix` without collision.

Within one home, multiple watchtowers must be supported.

A provider may implement isolation with directories, databases, profiles, projects, namespaces, or another mechanism. The adapter must bind every operation to the active zxro home and must not silently search unrelated namespaces.

## Concurrency contract

Assume 10 to 12 crews may complete near-simultaneously.

The composed store must guarantee:

- no corrupted durable state;
- no lost write after a successful command;
- no duplicated logical settlement event;
- unique ordered mailbox generations per watchtower;
- stable event IDs;
- independent, lock-safe handled state;
- deterministic conflict handling.

Lock-free concurrency is not required. Safe serialization is acceptable.

A provider that is single-writer may still conform if its adapter can serialize access locally without introducing a correctness gap. Requiring a resident server solely to make normal zxro concurrency safe is an operational tradeoff to record during provider evaluation, not a change to this semantic contract.

## Durability and crash safety

After a mutating operation reports success, its state must survive immediate caller exit.

Providers must fail closed on malformed, conflicting, or unsafe state. They must not guess through corruption.

Retries after uncertain process termination must be safe for operations that carry a stable identity. Settlement and mailbox publication use the committed event ID defined above.

Read ack and handled state are separate durable mutations. A crash after ack but before handling is safe because the event remains visible in `pending`.

## Machine-interface requirements for CLI adapters

An external CLI can back a zxro provider when an adapter can obtain deterministic machine behavior equivalent to:

```text
machine-readable structured output
errors on stderr
stable non-zero exit codes
non-interactive operation
stable identifiers
explicit store/namespace selection
```

JSON is preferred for provider CLIs but is not required if the adapter can parse another stable machine format without scraping human prose.

The zxro public CLI remains the integration boundary for Pi, Claude, humans, and scripts. Provider-specific commands stay behind the adapter.

## Provider dependencies

The zxro core and built-in v0 provider remain Python 3.11+ standard-library only.

Optional adapters may require external binaries or services. Those dependencies remain optional and must not become prerequisites for the built-in zxro CLI.

This allows evaluation of tools such as Beads or a local mail CLI without making them part of zxro's base installation.

## Conformance profile

A provider or provider composition is zxro-compatible when the adapter can satisfy all required semantics in this contract.

The conformance suite must cover at least:

- duplicate work creation;
- bounded current-state reads;
- work filtering by watchtower and state;
- turn creation and identity separation;
- idempotent settlement;
- conflicting terminal settlement;
- artifact reference resolution without eager body reads;
- concurrent settlements;
- stable event IDs and unique ordered mailbox generations;
- delta-only unread reads;
- monotonic read ack;
- ack advancing past an unhandled event without removing it from pending;
- out-of-order event handling;
- idempotent event handling;
- work close remaining independent from read ack and event handling;
- crash recovery between terminal-state commit and mailbox publication;
- fail-closed reads for missing or mismatched terminal turns and artifact metadata;
- empty unread/pending and one new settlement remaining independent of handled history size;
- missing-object reads leaving a nonexistent provider namespace uncreated;
- namespace isolation;
- progressive-disclosure and bounded-context invariants.

The built-in provider runs this suite in normal CI. Optional external adapters may run the same semantic suite as opt-in integration tests.

## Candidate evaluation checklist

When evaluating Beads or another work CLI, ask:

| Requirement | Level |
|---|---|
| Stable work IDs | Required |
| Current-state read without historical bodies | Required |
| Machine-readable output | Required |
| Filter by watchtower metadata | Required or cheaply adaptable |
| Store external turn/session references | Required or cheaply adaptable |
| Close without deleting history | Required |
| Explicit local namespace/store selection | Required |
| Safe 10 to 12 concurrent callers, directly or through adapter serialization | Critical |
| Idempotent updates | Required or adapter-emulated |
| No target-repository pollution | Strongly preferred |
| No mandatory resident service | Strongly preferred for local use |

When evaluating a mailbox CLI, ask:

| Requirement | Level |
|---|---|
| Publish to a watchtower/recipient | Required |
| Stable message/event identity | Required |
| Monotonic delivery position or safely emulatable sequence | Required |
| Compact machine-readable unread view | Required |
| Durable read acknowledgement separate from handled/done state | Required or safely adapter-emulated |
| Unhandled attention query independent from read state | Required or safely adapter-emulated |
| Out-of-order, idempotent handling | Required |
| History retained after ack/handle | Required |
| Body/evidence fetched separately | Required |
| Artifact/attachment references | Required or cheaply adaptable |
| Idempotent publication | Required or adapter-emulated |
| Multiple independent namespaces | Required |
| No mandatory resident service | Strongly preferred for local use |

Provider-specific extra capabilities such as dependencies, priorities, claims, full-text search, semantic search, threads, remote sync, or distributed storage are useful but not part of zxro v0 conformance.

## Compatibility and evolution

The durable-store contract is more stable than any provider schema.

Adapters may change their internal representation without changing zxro CLI behavior. A change to required object meaning, settlement ordering, mailbox delivery, read ack, attention handling, isolation, or progressive-disclosure behavior is a contract change and requires explicit compatibility review.

Provider-native IDs remain provider details unless promoted into an explicitly typed zxro field. zxro must not expose one provider's storage schema as the general contract.

## Related

- [Contracts index](./README.md)
- [Contract conventions](./conventions.md)
- [Product architecture](../product-architecture.md)
- [Decision 0002: Separate inbox delivery position from attention handling](../../decisions/0002-separate-delivery-from-attention.md)
- [v0.x CLI](../../v0.x/surfaces/cli.md)
- [Technology stack](../../v0.x/scope/technology-stack.md)
- [Testing and agent workflow](../../v0.x/engineering/testing-and-agent-workflow.md)
