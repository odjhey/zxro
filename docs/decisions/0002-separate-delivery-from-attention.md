---
name: decision_separate_delivery_from_attention
description: "Accepted decision to keep the inbox read cursor separate from per-event attention handling."
type: decision
tags: [decisions, v0.x, inbox, mailbox]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T16:03:00+08:00
updated_at: 2026-08-24T20:05:00+08:00
---

# 0002: Separate inbox delivery position from attention handling

## Context

The current v0.x CLI model uses one monotonic inbox generation and one `ack` cursor. `inbox pending` is defined as events newer than the cursor.

That is cheap and deterministic, but it quietly assumes the watchtower handles events in generation order. The assumption stops working when several crews report together and the operator wants to act on the most important item first. Advancing a cursor through a later generation can hide earlier events that were read but not actually handled.

Rozoro reached this problem at roughly the same target fleet size. Its target Watchtower Mailbox separates delivery batches from independently handled task-scoped attention. zxro does not need the full Rozoro mailbox schema, but it does need the same distinction.

## Options considered

### Keep generation-only acknowledgement

Treat every generation at or below `ack` as finished attention.

This is the smallest model, but it makes partial and out-of-order handling unsafe. The watchtower must keep the unhandled remainder in conversation memory or another ad-hoc list.

### Make each actionable inbox event independently handleable

Keep the immutable event log and monotonic generation, add a stable `event_id`, and persist handled state separately by event ID. The generation cursor records what has been observed; handled state records what no longer needs watchtower attention.

This adds one small durable concept while preserving the file-backed CLI design.

### Add a separate first-class mailbox-item object now

Introduce a second attention entity with its own identity, supersession graph, severity, and delivery membership.

This is the most flexible model, but v0.x settlement events are already task-scoped and independently actionable. A second entity would be speculative until zxro batches several reasons into one event or needs reason-level supersession.

## Choice

Make each actionable v0.x inbox event independently handleable. Do not add a separate mailbox-item object yet.

The intended model is:

```text
inbox event
  event_id      stable identity
  generation    monotonic order / read position
  work_id
  turn_id
  bounded routing context
  artifact references

read ack
  highest generation durably observed by the watchtower

handled state
  event_id -> handled_at
```

The CLI surface should distinguish:

```text
zxro inbox unread --watchtower <id>
zxro inbox pending --watchtower <id>
zxro inbox handle <event-id>
zxro ack --watchtower <id> --through <generation>
```

`unread` is the context-efficient delta feed: generations above the read cursor.

`pending` is the attention view: actionable events that have not been handled, regardless of read cursor position.

`handle` is idempotent and affects only per-event attention state. It does not rewrite the immutable inbox event and does not close the work item.

`ack` means “durably observed through generation N.” It must not mean “all attention through N is resolved.”

For v0.x, `turn settle` remains the operation that creates actionable inbox events. Registration, turn start, liveness, and other progress/diagnostic signals must not become inbox attention merely because they were observed.

## Consequences

- A watchtower can read a burst once, acknowledge the read position, then handle items in business-priority order without losing the remainder.
- Routine `unread` output stays bounded by new information; `pending` grows only with genuinely unresolved attention, not with old artifact size.
- Read acknowledgement, event handling, and `work close` have one meaning each.
- Inbox events need a stable `event_id` in addition to their monotonic generation.
- Handling state requires its own lock-safe durable file or record; it must not be represented by mutating append-only inbox history.
- A future notification coalescer may batch several events, but a delivery batch must never become the identity used to mark each event handled.
- A future separate mailbox-item entity remains available if one event later contains several independently actionable reasons or needs explicit supersession.

## Rule

M1 implements `pending` from handled state, not from read generation. The CLI spec and durable store contract carry the same rule.

Required acceptance behavior:

1. Read/ack may advance past an unhandled event without removing it from `inbox pending`.
2. `inbox handle <event-id>` may handle events out of generation order.
3. Handling the same event twice is idempotent.
4. `work close` is independent from read ack and event handling.
5. Old artifact bodies are never inlined by either `unread` or `pending`.

If a later design introduces coalesced delivery or several attention reasons per event, revisit whether a separate mailbox-item identity has become necessary.

## Related

- [Rozoro lessons report](../reports/2026-08-24-rozoro-lessons.md)
- [v0.x CLI](../v0.x/surfaces/cli.md)
- [Product architecture](../architecture/product-architecture.md)
