---
name: m2_operator_ergonomics_task_card
description: "M2 task card for operator ergonomics and manual diagnostics in the zxro CLI."
type: checklist
tags: [v0.x, execution, cli]
status: current
generated: "pi coding agent, 2026-08-24"
created_at: "2026-08-24T20:20:00+08:00"
updated_at: "2026-08-25T00:05:00+08:00"
---

# M2 operator ergonomics task card

## Outcome

Add `inspect`, `turn env`, and `turn bind` commands so operators can diagnose work and resume metadata without loading full artifact payloads.

## Dependencies

- M1 is complete and merged in PR #7 at base commit `7a3db5a`.
- CLI-first plan PR3 scope is active.
- Session binding semantics come from [`session-binding` contract](../../../architecture/contracts/session-binding.md).

## Scope

- Implement metadata-only inspection for one work item.
- Expose deterministic resume metadata via `turn env`.
- Add idempotent native session enrichment with conflict rejection via `turn bind`.
- Keep `inspect` and routine read commands free of raw artifact content.

Out of scope:

- Pi/Claude integrations.
- External durable providers.
- Wakeups, loops, daemons, or `turn run`.

## Contract rules

- `inspect <work-id>` is read-only and must not repair, ack, handle, reconcile, or print payload content.
- `turn env` must emit exactly the four `ZXRO_*` values already used by future resume tooling.
- `turn bind` may fill missing `native_session_id` or `native_session_source`; repeated writes with the same values are no-op.
- Conflicting identity updates fail closed instead of replacing existing values.

## Acceptance evidence

| Requirement | Executable evidence |
|---|---|
| `inspect` returns safe metadata and never inlines payloads | `InspectCliTests.test_inspect_reports_counts_and_bytes_without_inlining_payloads` |
| `turn bind` is idempotent and rejects conflicts | `TurnBindingCliTests.test_turn_bind_enriches_in_stages_and_rejects_conflicts` |
| resume metadata helpers stay correct and parseable | `TurnBindingCliTests.test_turn_env_outputs_exact_resume_metadata_and_shell_quotes_home` |
| progressive disclosure is preserved when old artifacts expand | `InspectCliTests.test_large_artifact_history_stays_behind_metadata` |
| manual full-loop walkthrough remains runnable | `FullLoopWalkthroughTests.test_disposable_full_loop_walkthrough` |

## Gates

- [x] Progressive disclosure and artifact-byte accounting in inspect remain stable.
- [x] `turn bind` uses immutable identity semantics from the session-binding contract.
- [x] `python3 -m unittest discover -s tests -v` passes for updated suite.
- [x] GitHub Actions passed on Python 3.11 and 3.12 across Ubuntu and macOS for exact head `d245b78` in [run 32747141626](https://github.com/odjhey/zxro/actions/runs/32747141626).
- [x] The CLI-spec full-loop block runs from a checkout with only the standard library and the `bin/zxro` shim.
- [ ] Independent architecture, security, and compatibility review approves the PR.

## Related

- [Task cards index](./README.md)
- [CLI-first delivery plan](../cli-first-delivery-plan.md)
- [Session binding contract](../../../architecture/contracts/session-binding.md)
- [v0.x CLI spec](../../surfaces/cli.md)