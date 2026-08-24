---
name: docs_guide
description: "How to explore and maintain this project's documentation corpus."
type: index
tags: [docs, meta]
status: current
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:24:31+08:00
---

# Documentation Guide

This directory is the project's documentation home. It is organized for progressive disclosure: start at an index, follow links only as deep as needed, and use frontmatter to identify a document before reading it.

## Layout

```text
docs/
├── README.md                 How to explore and maintain the docs
├── INDEX.md                  Flat table of contents
├── architecture/             Target-state system and domain design
│   ├── bounded-contexts/     Domain or capability boundaries
│   ├── contracts/            Published interfaces and shared types
│   └── diagrams/             Visual companions to prose
├── v0.x/                     Scope and delivery plans for the v0.x series
│   ├── scope/                Goals, boundaries, and technology choices
│   ├── execution/            Plans, decision gates, and task cards
│   ├── surfaces/             User- and system-facing interfaces
│   ├── engineering/          Runtime and quality strategy
│   └── validation/           Readiness and acceptance evidence
├── ai/                       Agent behavior policy
├── decisions/                Architecture and product decisions
├── playbooks/                Repeatable operating procedures
├── reports/                  Dated assessments and findings
└── scripts/                  Documentation tooling
```

## Reading paths

- **Understand the system** → [architecture/README.md](./architecture/README.md)
- **Understand the current delivery target** → [v0.x/README.md](./v0.x/README.md)
- **Find a term** → [architecture/ubiquitous-language.md](./architecture/ubiquitous-language.md)
- **Review prior choices** → [decisions/README.md](./decisions/README.md)
- **Find any document** → scan [INDEX.md](./INDEX.md) or use the [find-docs skill](../.agents/skills/find-docs/SKILL.md)
- **Write or revise documentation** → follow the [docs-and-writing skill](../.agents/skills/docs-and-writing/SKILL.md)

## Frontmatter schema

Every Markdown document starts with YAML frontmatter. Required fields:

```yaml
name: unique_snake_case_identifier
description: "One sentence describing the document."
type: index | architecture | bounded-context | contract | diagram | glossary | plan | spec | guide | checklist | reference | report | decision
```

Optional queryable fields:

```yaml
tags: [v0.x, runtime]
status: current | draft | archived | superseded
resource: path-or-url
generated: "tool or agent identity"
gate: 1
sources:
  - ref: path-or-url
    credibility: primary | secondary | inferred
verified: "reviewer and date"
stale_after: 2027-01-01
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
```

## Conventions

- Use relative links between documents.
- Give every directory a `README.md` index.
- Link each document from its nearest index and from [INDEX.md](./INDEX.md).
- Treat prose as authoritative; diagrams summarize it and must not introduce new behavior.
- Start terminology changes in the ubiquitous language and interface changes in contracts.
- Follow the [docs-and-writing skill](../.agents/skills/docs-and-writing/SKILL.md) for the canonical frontmatter template and house style.

## Maintenance rules

1. Bump `updated_at` after a material edit.
2. Add new documents to their directory index and [INDEX.md](./INDEX.md).
3. Mark replaced documents `superseded` and link to the replacement instead of deleting history.
4. Mark agent-produced material with `generated`; add `verified` only after human review.
5. Use `node docs/scripts/find-docs.mjs --stale` to identify documents requiring review.
