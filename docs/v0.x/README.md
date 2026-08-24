---
name: v0x_index
description: "Index for the v0.x durable-artifact CLI scope, execution plan, surfaces, engineering strategy, and validation."
type: index
tags: [v0.x]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:54:00+08:00
---

# v0.x

v0.x starts with a dependency-free durable-artifact CLI. The CLI is proven manually before Pi or Claude integrations automate it. Agent execution remains outside zxro and is exercised through acpx during later smoke tests.

Long-running work must stay cheap to reconcile. Routine reads expose bounded summaries, current state, and artifact references. Full reports and logs stay out of watchtower context until a caller deliberately asks for deeper evidence.

## Directory map

- [Scope](./scope/README.md) — outcomes, isolation boundaries, progressive context disclosure, and stack.
- [Execution](./execution/README.md) — milestones, gates, and task cards.
- [Surfaces](./surfaces/README.md) — CLI and other user/system interfaces.
- [Engineering](./engineering/README.md) — testing, runtime, durability, bounded reconciliation, and provisioning.
- [Validation](./validation/README.md) — acceptance and readiness evidence.

## Suggested reading order

1. [Goal and scope](./scope/goal-and-scope.md)
2. [Product architecture](../architecture/product-architecture.md)
3. [Ubiquitous language](../architecture/ubiquitous-language.md)
4. [v0.x CLI](./surfaces/cli.md)
5. [Technology stack](./scope/technology-stack.md)
6. [Implementation plan](./execution/implementation-plan.md)
7. [Testing and agent workflow](./engineering/testing-and-agent-workflow.md)
8. [Native session recovery](../playbooks/native-session-recovery.md)
9. [Release readiness](./validation/release-readiness.md)

[Back to docs](../README.md)
