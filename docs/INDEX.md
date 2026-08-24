---
name: docs_index
description: "Flat table of contents for every document in docs, grouped by area."
type: index
tags: [docs, meta, toc]
status: current
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:29:47+08:00
---

# Docs Index

Every document is listed here. See [README.md](./README.md) for the schema and maintenance rules.

## Meta

| Document | Type | Purpose |
|---|---|---|
| [Documentation guide](./README.md) | index | Corpus layout, schema, and conventions |
| [Docs index](./INDEX.md) | index | This flat table of contents |

## AI and agent policy

| Document | Type | Purpose |
|---|---|---|
| [AI docs](./ai/README.md) | index | Agent-policy index |
| [Agent policy](./ai/agent-policy.md) | guide | Human-readable agent rules placeholder |
| [Agent policy YAML](./ai/agent-policy.yaml) | — | Machine-readable policy placeholder |

## Architecture

| Document | Type | Purpose |
|---|---|---|
| [Architecture](./architecture/README.md) | index | Architecture reading path |
| [Product architecture](./architecture/product-architecture.md) | architecture | Product and system architecture template |
| [Ubiquitous language](./architecture/ubiquitous-language.md) | glossary | Canonical vocabulary |
| [Bounded contexts](./architecture/bounded-contexts/README.md) | index | Context index and guidance |
| [Context template](./architecture/bounded-contexts/context-template.md) | bounded-context | Template for a context or capability boundary |
| [Contracts](./architecture/contracts/README.md) | index | Contract index and stability rules |
| [Contract conventions](./architecture/contracts/conventions.md) | contract | Shared contract conventions placeholder |
| [Contract template](./architecture/contracts/contract-template.md) | contract | Template for a contract family |
| [Diagrams](./architecture/diagrams/README.md) | index | Diagram index and source-of-truth rule |
| [System context](./architecture/diagrams/system-context.md) | diagram | Starter system-context diagram |

## Decisions

| Document | Type | Purpose |
|---|---|---|
| [Decision records](./decisions/README.md) | index | Decision format and index |
| [Decision template](./decisions/0000-template.md) | decision | Copyable decision-record template |

## v0.x

| Document | Type | Purpose |
|---|---|---|
| [v0.x](./v0.x/README.md) | index | v0.x planning and delivery index |
| [Scope](./v0.x/scope/README.md) | index | Scope document index |
| [Goal and scope](./v0.x/scope/goal-and-scope.md) | plan | Outcomes, boundaries, and success criteria |
| [Technology stack](./v0.x/scope/technology-stack.md) | reference | Technology choices and constraints |
| [Execution](./v0.x/execution/README.md) | index | Execution document index |
| [Implementation plan](./v0.x/execution/implementation-plan.md) | plan | Milestones and sequencing |
| [Human decision gates](./v0.x/execution/human-decision-gates.md) | guide | Decisions requiring human approval |
| [Task cards](./v0.x/execution/task-cards/README.md) | index | Task-card index and usage |
| [Task-card template](./v0.x/execution/task-cards/task-card-template.md) | plan | Copyable implementation task card |
| [Surfaces](./v0.x/surfaces/README.md) | index | Product-surface index |
| [Surface template](./v0.x/surfaces/surface-template.md) | spec | Template for a user or system surface |
| [Engineering](./v0.x/engineering/README.md) | index | Engineering strategy index |
| [Testing and agent workflow](./v0.x/engineering/testing-and-agent-workflow.md) | guide | Quality and automation strategy |
| [Runtime and provisioning](./v0.x/engineering/runtime-and-provisioning.md) | guide | Runtime and environment strategy |
| [Validation](./v0.x/validation/README.md) | index | Validation document index |
| [Release readiness](./v0.x/validation/release-readiness.md) | checklist | Acceptance and readiness template |

## Operations and reports

| Document | Type | Purpose |
|---|---|---|
| [Playbooks](./playbooks/README.md) | index | Operational playbook index |
| [Documentation update](./playbooks/documentation-update.md) | guide | Keeping architecture docs aligned with changes |
| [Reports](./reports/README.md) | index | Dated assessments and findings |

Reusable documentation skills:

- [find-docs](../.agents/skills/find-docs/SKILL.md) discovers and filters the corpus.
- [docs-and-writing](../.agents/skills/docs-and-writing/SKILL.md) defines the frontmatter template, house style, and maintenance workflow.
- [unslop](../.agents/skills/unslop/SKILL.md) removes AI writing patterns and restores a human voice.

All three are exposed to Claude-compatible harnesses through `.claude/skills`.
