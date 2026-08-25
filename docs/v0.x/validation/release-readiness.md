---
name: v0x_release_readiness
description: "Template checklist for v0.x acceptance evidence, operational readiness, and release approval."
type: checklist
tags: [v0.x, validation, release]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T09:17:50+08:00
---

# v0.x release readiness

## Product acceptance

- [ ] Success criteria in [goal and scope](../scope/goal-and-scope.md) pass.
- [x] The M0/M1 operator-driven multi-turn flow has [merged acceptance evidence](./cli-multiturn-operator-readiness.md).
- [x] Current M0/M1 limitations are recorded in the [CLI multi-turn operator-readiness report](./cli-multiturn-operator-readiness.md#limits-and-compatibility).

These checks cover the built-in local provider and operator-driven public CLI only. They do not prove M2 or M3 native recovery, optional adapters, live Claude smoke, Pi or Claude release integration, M7 automation, deployment, migration, health checks, rollback, or v0.x release approval.

## Engineering readiness

- [x] M0/M1 required checks passed on PR [#17](https://github.com/odjhey/zxro/pull/17) and in the [post-merge `master` CI run](https://github.com/odjhey/zxro/actions/runs/32795552021).
- [ ] Configuration and secrets are validated.
- [ ] Deployment, migration, health check, and rollback procedures are proven.
- [ ] Logs and failure diagnostics are adequate.

## Documentation readiness

- [ ] Architecture, contracts, terminology, and decisions match behavior for the full v0.x scope.
- [x] M0/M1 operator instructions match the merged CLI evidence.

## Approval

| Role | Decision | Evidence link | Date |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Related

- [Validation index](./README.md)
- [Human decision gates](../execution/human-decision-gates.md)
