---
name: docs_index
description: "Flat table of contents for every document in docs, grouped by area."
type: index
tags: [docs, meta, toc]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:33:00+08:00
---

# Docs index

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
| [Product architecture](./architecture/product-architecture.md) | architecture | zxro ownership boundaries, identities, watchtower/crew cwd split, and end-to-end flow |
| [Ubiquitous language](./architecture/ubiquitous-language.md) | glossary | Canonical watchtower, work, turn, session, inbox, generation, ack, and wake terms |
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
| [0001: Build the v0 CLI first with Python stdlib](./decisions/0001-v0-cli-first-python-stdlib.md) | decision | Dependency-free Python CLI first; harness integrations and compiled rewrite deferred |

## v0.x

| Document | Type | Purpose |
|---|---|---|
| [v0.x](./v0.x/README.md) | index | v0.x durable-artifact CLI and delivery index |
| [Scope](./v0.x/scope/README.md) | index | Scope document index |
| [Goal and scope](./v0.x/scope/goal-and-scope.md) | plan | Outcomes, boundaries, success criteria, and CLI-first exit criteria |
| [Technology stack](./v0.x/scope/technology-stack.md) | reference | Python 3.11+ stdlib, filesystem durability, unittest, acpx boundary, and deferred choices |
| [Execution](./v0.x/execution/README.md) | index | Execution document index |
| [Implementation plan](./v0.x/execution/implementation-plan.md) | plan | Artifact CRUD through inbox/ack, then Pi/Claude integration and watchtower loop |
| [Human decision gates](./v0.x/execution/human-decision-gates.md) | guide | Decisions requiring human approval |
| [Task cards](./v0.x/execution/task-cards/README.md) | index | Task-card index and usage |
| [Task-card template](./v0.x/execution/task-cards/task-card-template.md) | plan | Copyable implementation task card |
| [Surfaces](./v0.x/surfaces/README.md) | index | Product-interface index |
| [v0.x CLI](./v0.x/surfaces/cli.md) | spec | Command descriptions and behavior for durable artifact CRUD, settlement, inbox, ack, inspection, and metadata helpers |
| [Surface template](./v0.x/surfaces/surface-template.md) | spec | Template for a later user or system interface |
| [Engineering](./v0.x/engineering/README.md) | index | Engineering strategy index |
| [Testing and agent workflow](./v0.x/engineering/testing-and-agent-workflow.md) | guide | Dependency-free black-box CLI tests, durability invariants, and later harness smoke tests |
| [Runtime and provisioning](./v0.x/engineering/runtime-and-provisioning.md) | guide | No-daemon local topology, `$ZXRO_HOME`, metadata environment, locking, and recovery posture |
| [Validation](./v0.x/validation/README.md) | index | Validation document index |
| [Release readiness](./v0.x/validation/release-readiness.md) | checklist | Acceptance and readiness template |

## Operations and reports

| Document | Type | Purpose |
|---|---|---|
| [Playbooks](./playbooks/README.md) | index | Operational playbook index |
| [Documentation update](./playbooks/documentation-update.md) | guide | Keeping architecture docs aligned with changes |
| [Native session recovery](./playbooks/native-session-recovery.md) | guide | Last-resort Pi/Claude session lookup and direct resume without confusing acpx and native IDs |
| [Reports](./reports/README.md) | index | Dated assessments and findings |

Reusable documentation skills:

- [find-docs](../.agents/skills/find-docs/SKILL.md) discovers and filters the corpus.
- [docs-and-writing](../.agents/skills/docs-and-writing/SKILL.md) defines the frontmatter template, house style, and maintenance workflow.
- [unslop](../.agents/skills/unslop/SKILL.md) removes AI writing patterns and restores a human voice.

All three are exposed to Claude-compatible harnesses through `.claude/skills`.
