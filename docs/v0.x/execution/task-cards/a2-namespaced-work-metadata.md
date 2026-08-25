---
name: a2_namespaced_work_metadata_task_card
description: "Task card for bounded namespaced metadata on work records with the work meta command family, validation, and conformance tests."
type: checklist
tags: [v0.x, execution, task-cards, cli, metadata]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-25T19:21:34+08:00"
---

# A2 — Namespaced work metadata

Implements WP2 of the [machine contract design](../machine-contract-design.md) (issue #26).

## Outcome

Work records store and return bounded namespaced metadata through `zxro work meta set|show|unset`, the data round-trips unchanged through the work lifecycle, and `--json` output exposes it inside the versioned envelope.

## Inputs and dependencies

- Stacked on [A1](./a1-versioned-json-envelope.md): metadata must never ship on an unversioned wire shape. Do not start review before A1 merges; implementation may proceed on a branch stacked on A1's.
- Independent of lanes B, C, and D. One deliberate seam with lane C: card [C1](./c1-per-turn-artifacts.md) defers per-turn external references to this metadata mechanism, so A2's validation function must be reusable beyond work records even though only work records use it now.

## In scope

- Reusable validation implementing design D4: namespace and key pattern `[a-z0-9][a-z0-9._-]{0,63}`, depth limit 4, string values at most 2,048 characters after NFC normalization, 16 KiB total serialized metadata, allowed types only (object, string, integer, boolean, arrays of those scalars), reserved `zxro` namespace.
- Persistence in the built-in provider; absent metadata is omitted, never `null`.
- `work meta set` (whole-namespace replace from stdin JSON, under the home lock), `work meta show` (all or one namespace), `work meta unset` (idempotent), including on closed work.
- `metadata` in `work show` and `work list`; human list output summarizes to namespace names to stay one line per work item.
- Conformance tests: round-trip through create, meta set, close, and turn settle; namespace isolation across namespaces and homes; every bound at its limit; malformed input at exit class 2; malformed durable state at exit class 5; reserved-namespace rejection.
- Durable store contract and CLI spec updates in the same PR.

## Out of scope

- Metadata on watchtower, turn, or artifact records.
- Typed external-reference structures (rejected for v0.x in the design).
- Secret detection; the docs state the policy, nothing scans values.
- The work brief (card [C2](./c2-work-brief.md) uses artifacts, not metadata).

## Contract

| Produces | Consumes | Must not change |
|---|---|---|
| `work meta` commands; `metadata` field in work payloads; reusable validation | A1 envelope; design D3, D4, D5; home lock | Work identity, state, and lifecycle semantics; settlement and mailbox behavior; bounded routine reads |

## Steps

1. Implement and unit-test the validation function against every D4 bound.
2. Add persistence and the three commands; document the older-binary exit-class-5 downgrade in conventions.
3. Expose metadata in work output, then add the conformance cases.
4. Update the durable store contract's work object and `work.update` sections and the CLI spec.

## Operator decisions

The implementation records these approved contract choices:

- older binaries may reject metadata-bearing work records with exit class 5;
- a namespace payload root counts as depth 1;
- `work meta show <work-id> <missing-namespace>` exits with class 3.

## Acceptance criteria

- [x] Bounded namespaced metadata survives all lifecycle operations unless explicitly updated.
- [x] Namespace writes replace only the named namespace; concurrent writers cannot corrupt or interleave state.
- [x] All D4 bounds are enforced at the documented exit classes.
- [x] `--json` exposure rides the A1 envelope as an additive field with no version bump.
- [x] Core behavior stays provider-neutral; no namespace is interpreted by core.

## Verification

```sh
python3 -m unittest discover -s tests -v
printf '{"issue_id":"bd-a19f"}' | bin/zxro work meta set <work-id> beads --stdin
bin/zxro --json work show <work-id>   # metadata present inside data
```

## Documentation impact

- [x] Durable store contract, CLI spec, and conventions updated in this PR.
- [x] Machine contract design WP2 marked delivered.

## Human gate

Contract compatibility review, and confirmation that the durable-record downgrade behavior (older binary rejects metadata-carrying records) is acceptable.

## Related

- [Machine contract design](../machine-contract-design.md)
- [A1 versioned JSON envelope](./a1-versioned-json-envelope.md)
- [Task-card index](./README.md)
