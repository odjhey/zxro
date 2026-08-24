---
name: v0x_release_readiness
description: "Template checklist for v0.x acceptance evidence, operational readiness, and release approval."
type: checklist
tags: [v0.x, validation, release]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T00:29:00+08:00
---

# v0.x Release Readiness

## Product acceptance

- [ ] Success criteria in [goal and scope](../scope/goal-and-scope.md) pass.
- [ ] Primary user flows have recorded evidence.
- [ ] Known limitations are documented.

## M2 operator ergonomics evidence

- [x] `inspect <work-id>` read-only metadata is available and does not inline payloads.
- [x] `turn env` returns stable resume keys (`ZXRO_TURN_ID`, `ZXRO_WORK_ID`, `ZXRO_WATCHTOWER_ID`, `ZXRO_HOME`) for a turn.
- [x] `turn bind` is idempotent for repeated enrichments and rejects conflicting native identities.
- [x] Native-session provenance uses a bounded grammar, and the pre-M2 rollback consequence is documented.
- [x] Provider-neutral M2 conformance covers binding, missing objects, read-only behavior, provenance rejection, inspection, and corruption.
- [x] Progressive-disclosure behavior remains stable when older artifact records grow.
- [x] The manual loop walkthrough in the CLI spec runs verbatim in a disposable home without an external runtime binary.

| Requirement | Evidence |
|---|---|
| Metadata inspection and no-payload output | `InspectCliTests.test_inspect_reports_counts_and_bytes_without_inlining_payloads` |
| Resume metadata helper output | `TurnBindingCliTests.test_turn_env_outputs_exact_resume_metadata_and_shell_quotes_home` |
| Session binding idempotency and conflict rejection | `TurnBindingCliTests.test_turn_bind_enriches_in_stages_and_rejects_conflicts` |
| Provenance grammar and rollback boundary | `TurnBindingCliTests.test_native_session_source_uses_bounded_provenance_grammar` and `test_m1_rollback_rejects_m2_native_source_records`; [session binding contract](../../architecture/contracts/session-binding.md) |
| Provider-neutral M2 behavior | `BuiltinM1ProviderConformance.test_native_binding_is_immutable_and_staged`, `test_m2_missing_objects_have_no_side_effects`, `test_m2_inspect_is_read_only`, `test_native_provenance_rejects_unbounded_or_unsafe_values`, `test_m2_artifact_metadata_corruption_fails_closed`, and `test_inspect_returns_bounded_work_metadata` through `M2ProviderConformance` |
| Progressive disclosure against record growth | `InspectCliTests.test_large_artifact_history_stays_behind_metadata` |
| Disposable end-to-end manual loop | `FullLoopWalkthroughTests.test_disposable_full_loop_walkthrough`; CLI-spec block uses the `bin/zxro` shim, manual settlement, and a captured JSON event ID |
| Immutable implementation-head suite | Last code-bearing commit `3a0e939`; [GitHub Actions run 32750988935](https://github.com/odjhey/zxro/actions/runs/32750988935) passed Python 3.11 and 3.12 on Ubuntu and macOS |
| Final PR-head CI | Verified externally through the [PR #8 GitHub checks](https://github.com/odjhey/zxro/pull/8/checks); this row intentionally carries no self-referential SHA claim |

The implementation-head row is immutable evidence for the code-bearing change. Documentation-only commits may advance the PR head without changing that row. GitHub's PR checks are authoritative for the current head.

## Engineering readiness

- [ ] Required automated checks pass.
- [ ] Configuration and secrets are validated.
- [ ] Deployment, migration, health check, and rollback procedures are proven.
- [ ] Logs and failure diagnostics are adequate.

## Documentation readiness

- [ ] Architecture, contracts, terminology, and decisions match behavior.
- [ ] Operator and user instructions are current.

## Approval

| Role | Decision | Evidence link | Date |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Related

- [Validation index](./README.md)
- [Human decision gates](../execution/human-decision-gates.md)
