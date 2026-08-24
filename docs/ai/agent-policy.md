---
name: agent_policy
description: "Placeholder for repository-specific rules governing coding agents and automated changes."
type: guide
tags: [ai, agents, policy]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
---

# Agent Policy

> TODO: Replace this scaffold with project-specific policy.

## Sources of truth

- Define which documents and code own product behavior, terminology, and contracts.
- Define precedence when instructions conflict.

## Required workflow

1. Inspect relevant repository context before changing files.
2. Make the smallest coherent change.
3. Update affected documentation.
4. Run appropriate checks.
5. Report changed files, verification, and unresolved risks.

## Human gates

Document actions that require explicit approval, such as destructive operations, releases, migrations, security changes, and external side effects.

## Safety boundaries

Document secrets handling, data access, allowed tools, network rules, and rollback expectations.

## Related

- [AI docs index](./README.md)
- [Human decision gates](../v0.x/execution/human-decision-gates.md)
