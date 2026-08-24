---
name: v0x_testing_and_agent_workflow
description: "Template for v0.x test strategy, automated checks, agent workflow, and completion evidence."
type: guide
tags: [v0.x, engineering, testing, agents]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
---

# v0.x Testing and Agent Workflow

## Quality goals

- TODO

## Test layers

| Layer | Purpose | Isolation | Required in CI |
|---|---|---|---|
| Unit | TODO | TODO | TODO |
| Integration | TODO | TODO | TODO |
| End-to-end | TODO | TODO | TODO |

## Required checks

```sh
# TODO: format, lint, typecheck, test, build, and docs checks
```

## Agent workflow

1. Read the task, nearby code, and relevant docs.
2. Implement the smallest coherent change.
3. Run focused checks, then the required suite.
4. Update docs and attach evidence.
5. Stop at documented human gates.

## Test data and isolation

TODO: Define fixtures, cleanup, concurrency, secrets, and external-service policy.

## Related

- [Engineering index](./README.md)
- [Agent policy](../../ai/agent-policy.md)
