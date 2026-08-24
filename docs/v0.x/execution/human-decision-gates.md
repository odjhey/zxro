---
name: v0x_human_decision_gates
description: "Placeholder for v0.x decisions and actions that require explicit human approval."
type: guide
tags: [v0.x, execution, gates]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
---

# v0.x Human Decision Gates

Agents and automation must stop at these gates until an authorized operator records a decision.

| Gate | Trigger | Decision required | Required evidence | Decision record |
|---|---|---|---|---|
| 0 | Scope is ready for implementation | Approve goal, boundaries, and success criteria | Reviewed scope docs | TODO |
| 1 | Architecture or stack choices become binding | Approve irreversible or costly choices | Options and trade-offs | TODO |
| 2 | Release is ready | Approve external release or deployment | Readiness checklist | TODO |

## Recording decisions

Record durable choices in [decision records](../../decisions/README.md). Record temporary approval evidence in the relevant task, pull request, or release record.

## Related

- [Execution index](./README.md)
- [Release readiness](../validation/release-readiness.md)
