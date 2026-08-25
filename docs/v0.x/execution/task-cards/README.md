---
name: v0x_task_cards_index
description: "Index and usage guidance for independently executable v0.x implementation task cards."
type: index
tags: [v0.x, execution, task-cards]
status: current
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T14:25:09+08:00
---

# v0.x Task Cards

Task cards turn the implementation plan into bounded units with explicit inputs, outputs, dependencies, checks, and documentation impact.

- [M1 durable settlement](./m1-durable-settlement.md) records scope, compatibility decisions, and executable acceptance evidence.
- [Task-card template](./task-card-template.md)

Name cards with an ordering or lane prefix when useful, for example `a1-foundation.md` or `b2-cli-surface.md`.

## Machine contract and MR lanes

These cards implement the [machine contract design](../machine-contract-design.md) (issues #25 and #26) and the [ZR1-ZR4 delivery plan](../rozoro-requirements-plan.md) (milestone MR). Lanes run in parallel; cards within a lane are stacked and merge in order.

```text
lane A  a1 versioned JSON envelope ──► a2 namespaced work metadata
lane B  b1 structured verdict ──► unblocks Pi (#16) and Claude (#15) integrations
lane C  c1 per-turn artifacts ──► c2 work brief
lane D  d1 turn bind
```

- [A1 versioned JSON envelope](./a1-versioned-json-envelope.md) wraps all public `--json` output and publishes the compatibility policy.
- [A2 namespaced work metadata](./a2-namespaced-work-metadata.md) adds bounded namespaced metadata to work records; stacked on A1.
- [B1 structured verdict](./b1-structured-verdict.md) separates routing verdict from execution outcome on settlement; gated on the verdict-vocabulary sign-off.
- [C1 per-turn artifacts](./c1-per-turn-artifacts.md) adds `artifact put` with kind-unique references and evidence frozen at settlement.
- [C2 work brief](./c2-work-brief.md) adds the set-once work-scoped brief artifact; stacked on C1.
- [D1 turn bind](./d1-turn-bind.md) implements late native-session-ID binding; smallest card, no dependencies.

Cross-lane rule: A1 rewrites every `--json` test assertion, so cards B1, C1, C2, and D1 assert JSON shapes through A1's envelope-tolerant test helper (or an equivalent local shim until it exists) and stay merge-order independent from lane A. Four developers can start a1, b1, c1, and d1 on day one.

[Back to execution](../README.md)
