---
name: docs_index
description: "Flat table of contents for every document in docs, grouped by area."
type: index
tags: [docs, meta, toc]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T09:35:45+08:00
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
| [Product architecture](./architecture/product-architecture.md) | architecture | zxro ownership boundaries, provider adapters, progressive context disclosure, mailbox attention, isolation, and end-to-end flow |
| [Ubiquitous language](./architecture/ubiquitous-language.md) | glossary | Canonical watchtower, work, turn, runtime/session, DATA/CONTROL, inbox, generation, ack, and handled terms |
| [Bounded contexts](./architecture/bounded-contexts/README.md) | index | Context index and guidance |
| [Context template](./architecture/bounded-contexts/context-template.md) | bounded-context | Template for a context or capability boundary |
| [Contracts](./architecture/contracts/README.md) | index | Contract index and stability rules |
| [Durable store contract](./architecture/contracts/durable-store.md) | contract | Provider-neutral work, turn, artifact, delivery, read ack, handled state, concurrency, crash recovery, and adapter conformance semantics |
| [Session binding contract](./architecture/contracts/session-binding.md) | contract | Durable work/turn-to-runtime address and optional provider-native conversation identity |
| [Agent runtime port](./architecture/contracts/agent-runtime-port.md) | contract | Transport-neutral start, DATA, CONTROL, status, and exact-resume boundary around acpx/native runtimes |
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
| [0002: Separate inbox delivery position from attention handling](./decisions/0002-separate-delivery-from-attention.md) | decision | Accepted split between read acknowledgement and independently handled inbox events |

## v0.x

| Document | Type | Purpose |
|---|---|---|
| [v0.x](./v0.x/README.md) | index | v0.x durable-artifact CLI and delivery index |
| [Scope](./v0.x/scope/README.md) | index | Scope document index |
| [Goal and scope](./v0.x/scope/goal-and-scope.md) | plan | Outcomes, provider boundary, isolation, mailbox attention, bounded context, success criteria, and CLI-first exit criteria |
| [Technology stack](./v0.x/scope/technology-stack.md) | reference | Python 3.11+ stdlib core, built-in local provider, optional storage adapters, unittest, and acpx boundary |
| [Execution](./v0.x/execution/README.md) | index | Execution document index |
| [Implementation plan](./v0.x/execution/implementation-plan.md) | plan | Contract-first built-in provider, delivery/read/attention mailbox, optional adapters, then Pi/Claude integration and watchtower loop |
| [CLI-first delivery plan](./v0.x/execution/cli-first-delivery-plan.md) | plan | Three stacked PRs with parallel test/docs tracks, repository layout, locked implementation decisions, and test-to-contract mapping for M0–M2 |
| [CLI-first Web UI plan](./v0.x/execution/web-ui-plan.md) | plan | Local view-only UI through public CLI reads, parity gates, future read contracts, security boundaries, and evidence-linked analysis |
| [Human decision gates](./v0.x/execution/human-decision-gates.md) | guide | Decisions requiring human approval |
| [Task cards](./v0.x/execution/task-cards/README.md) | index | Task-card index and usage |
| [M1 durable settlement](./v0.x/execution/task-cards/m1-durable-settlement.md) | checklist | M1 scope, compatibility decisions, and executable acceptance evidence |
| [Task-card template](./v0.x/execution/task-cards/task-card-template.md) | plan | Copyable implementation task card |
| [Surfaces](./v0.x/surfaces/README.md) | index | Product-interface index |
| [v0.x CLI](./v0.x/surfaces/cli.md) | spec | Current durable CRUD, settlement, mailbox, and artifact resolution plus unavailable future M2 inspection and metadata helpers |
| [Surface template](./v0.x/surfaces/surface-template.md) | spec | Template for a later user or system interface |
| [Engineering](./v0.x/engineering/README.md) | index | Engineering strategy index |
| [Testing and agent workflow](./v0.x/engineering/testing-and-agent-workflow.md) | guide | Black-box CLI tests, durable-store conformance, delivery/attention separation, bounded reconciliation, crash-gap tests, and later integration smoke tests |
| [Runtime and provisioning](./v0.x/engineering/runtime-and-provisioning.md) | guide | No-daemon/no-listener topology, runtime-port boundary, `$ZXRO_HOME`, metadata environment, locking, and recovery posture |
| [Validation](./v0.x/validation/README.md) | index | Validation document index |
| [Release readiness](./v0.x/validation/release-readiness.md) | checklist | Acceptance and readiness template |
| [CLI multi-turn operator readiness](./v0.x/validation/cli-multiturn-operator-readiness.md) | report | Public-CLI behavioral and manual evidence for an operator-driven multi-turn work lifecycle |

## Operations and reports

| Document | Type | Purpose |
|---|---|---|
| [Playbooks](./playbooks/README.md) | index | Operational playbook index |
| [Documentation update](./playbooks/documentation-update.md) | guide | Keeping architecture docs aligned with changes |
| [Native session recovery](./playbooks/native-session-recovery.md) | guide | Last-resort Pi/Claude session lookup and direct resume without confusing acpx and native IDs |
| [Reports](./reports/README.md) | index | Dated assessments and findings |
| [2026-08-25: Optional provider evaluation](./reports/2026-08-25-optional-provider-evaluation.md) | report | Beads and BSD `mailx` evidence, decisions, and implementation gates against the M0/M1 durable-store contract |
| [2026-08-24: Rozoro lessons for zxro](./reports/2026-08-24-rozoro-lessons.md) | report | Operational lessons to copy, adapt, or deliberately not port from Rozoro |

Reusable documentation skills:

- [find-docs](../.agents/skills/find-docs/SKILL.md) discovers and filters the corpus.
- [docs-and-writing](../.agents/skills/docs-and-writing/SKILL.md) defines the frontmatter template, house style, and maintenance workflow.
- [unslop](../.agents/skills/unslop/SKILL.md) removes AI writing patterns and restores a human voice.

All three are exposed to Claude-compatible harnesses through `.claude/skills`.
