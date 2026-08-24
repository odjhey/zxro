---
name: m1_durable_settlement_task_card
description: "M1 task card and acceptance evidence for durable turn settlement, artifacts, mailbox delivery, read acknowledgement, and handled state."
type: checklist
tags: [v0.x, execution, cli, mailbox]
status: current
generated: "pi coding agent, 2026-08-24"
created_at: "2026-08-24T20:05:00+08:00"
updated_at: "2026-08-24T22:20:00+08:00"
---

# M1 durable settlement task card

## Outcome

Add durable terminal turn results and bounded mailbox events without changing M0 command behavior for running turns.

## Scope

M1 includes `turn settle`, stdin artifacts, `artifact path`, `inbox unread`, `inbox pending`, `inbox handle`, and `ack`. Pi and Claude integrations, external providers, wakeups, and resident processes remain out of scope.

M1 depends on merged PR #6 at commit `7dbb533` and accepts [decision 0002](../../../decisions/0002-separate-delivery-from-attention.md).

## Contract decisions

- Outcome, NFC-normalized summary, and payload digest define retry equality. `source` records the first writer and does not participate in equality.
- A retry may omit stdin. If it supplies stdin, the bytes must match the first payload. A first settlement without stdin cannot gain a payload on retry.
- Settlement allocates the UUIDv4-based event ID before it commits the terminal turn. Mailbox publication assigns generation under the home lock.
- Event identity is durable settlement metadata. Crash-gap repair reuses it.
- The built-in provider stores each immutable event and handled marker as a separate bounded record. Per-watchtower high-water and unresolved indexes plus a direct event-ID index keep reads independent of handled and unrelated history.
- Mailbox reads resolve and compare the terminal turn and every referenced artifact metadata record before exposing an event. Missing or mismatched links fail with unsafe-state exit 5.
- Missing-object and read-like M1 commands open state without creating it. A nonexistent home remains absent after exit 3.
- Immutable event, direct index, and mailbox commits are individually resumable. Before/after faults at every write and an interleaved settlement cannot overwrite an event or hide a committed result.
- CLI handlers receive provider-neutral settlement, mailbox, and artifact capabilities. Reusable M1 conformance cases do not import the built-in provider; built-in setup and read-budget instrumentation stay in its fixture.
- Stdin reads stop at the supported limit plus one byte before hashing, hex encoding, or JSON encoding.
- Running M0 turn records remain valid. M1 adds fields only at settlement.
- An M0 binary cannot decode an M1 settled turn. Rollback tests must use a copied pre-settlement home or a fresh home.

## Acceptance evidence

| Requirement | Executable evidence |
|---|---|
| Identical retry and absent retry payload are idempotent; changed payload conflicts | `DurableLoopCliTests.test_settlement_idempotency_payload_and_artifact` |
| Changed terminal result conflicts; unknown turn publishes nothing; summary bound applies | `DurableLoopCliTests.test_conflicts_bounds_unknown_and_filters` |
| Crash after turn commit repairs one stable event | `DurableLoopCliTests.test_crash_gap_retry_preserves_event_identity` |
| Generations 1 through 10 remain pending after ack; handling 8 and 3 is independent and idempotent | `DurableLoopCliTests.test_read_ack_handled_and_work_close_are_independent` |
| Twelve concurrent settlements lose no successful write and assign unique ordered generations | `DurableLoopCliTests.test_concurrent_settlements_have_unique_ordered_generations` |
| Raw stdin stays behind an artifact reference and out of the event envelope | `DurableLoopCliTests.test_settlement_idempotency_payload_and_artifact` |
| Oversized input is rejected before settlement; malformed or changed artifact evidence fails closed | `DurableLoopCliTests.test_oversized_artifact_is_rejected_before_settlement` and `test_artifact_corruption_fails_closed` |
| Missing or mismatched terminal turns and artifact metadata fail closed | `DurableLoopCliTests.test_inbox_fails_closed_for_missing_terminal_turn_or_artifact`, `test_artifact_digest_and_unresolved_owner_are_cross_checked`, plus reusable M1 conformance coverage |
| Publication resumes around every event/index/mailbox write without overwrite, including an interleaved settlement | `DurableLoopCliTests.test_three_record_publication_resumes_without_overwrite` |
| Stdin overflow is rejected before settlement using a file-backed oversized input | `DurableLoopCliTests.test_oversized_artifact_is_rejected_before_settlement` |
| M1 settlement, conflict, delivery, ack, handling, concurrency, crash repair, isolation, progressive-disclosure, missing-object, corruption, and scaling semantics are reusable across provider fixtures | All cases in `M1ProviderConformance`, run by `BuiltinM1ProviderConformance` |
| Empty unread/pending and one new settlement do not read handled history | `M1ProviderConformance.test_empty_views_and_new_settlement_ignore_handled_history` |
| A handle between index and mailbox commit remains handled after repair | `DurableLoopCliTests.test_handle_between_index_and_mailbox_survives_repair` |
| Malformed next publication leaves the requested turn running | `DurableLoopCliTests.test_malformed_next_event_leaves_requested_turn_running` |
| Ack rejects missing terminal or intermediate generations without advancing | `DurableLoopCliTests.test_ack_rejects_missing_terminal_and_intermediate_generations_without_advancing` |
| Missing M1 objects leave a nonexistent home untouched | `MissingM1ObjectsHaveNoSideEffects.test_missing_commands_do_not_create_home` |
| M0 CRUD, isolation, malformed-state, path, lock, and atomic-write behavior remains intact | Existing conformance and `LocalFsInvariantTests` suite |

## Gates

- [x] ADR 0002 accepted.
- [x] Retry equality and durable event identity recorded.
- [x] Focused black-box tests pass locally on Python 3.11+.
- [ ] GitHub Actions passes on Python 3.11 and 3.12 across Ubuntu and macOS.
- [ ] Independent architecture, security, and compatibility review approves the PR.

## Related

- [Task cards index](./README.md)
- [CLI-first delivery plan](../cli-first-delivery-plan.md)
- [Durable store contract](../../../architecture/contracts/durable-store.md)
- [Contract conventions](../../../architecture/contracts/conventions.md)
