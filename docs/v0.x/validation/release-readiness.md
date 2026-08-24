---
name: v0x_release_readiness
description: "Template checklist for v0.x acceptance evidence, operational readiness, and release approval."
type: checklist
tags: [v0.x, validation, release]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T23:42:00+08:00
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
- [x] Progressive-disclosure behavior remains stable when older artifact records grow.
- [x] The manual loop walkthrough in the CLI spec runs in a disposable home.

| Requirement | Evidence |
|---|---|
| Metadata inspection and no-payload output | `InspectCliTests.test_inspect_reports_counts_and_bytes_without_inlining_payloads` |
| Resume metadata helper output | `TurnBindingCliTests.test_turn_env_outputs_exact_resume_metadata_and_shell_quotes_home` |
| Session binding idempotency and conflict rejection | `TurnBindingCliTests.test_turn_bind_enriches_in_stages_and_rejects_conflicts` |
| Progressive disclosure against record growth | `InspectCliTests.test_large_artifact_history_stays_behind_metadata` |
| Disposable end-to-end manual loop | `FullLoopWalkthroughTests.test_disposable_full_loop_walkthrough` |
| Cross-platform automated suite | [GitHub Actions run 32746944228](https://github.com/odjhey/zxro/actions/runs/32746944228), Python 3.11 and 3.12 on Ubuntu and macOS, exact head `1617ecb` |

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
