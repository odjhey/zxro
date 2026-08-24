---
name: bounded_contexts_index
description: "Index and guidance for documenting domain or capability boundaries."
type: index
tags: [architecture, domain, bounded-contexts]
status: current
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
---

# Bounded Contexts

Use one file per meaningful domain or capability boundary. Each document should define ownership, language, inputs, outputs, invariants, dependencies, and exclusions.

- [Context template](./context-template.md)

Replace the template with named context documents as the architecture develops.

## Relationship guidance

For every context relationship, record:

- upstream and downstream ownership;
- the contract crossing the boundary;
- synchronous or asynchronous interaction;
- consistency and failure expectations.

[Back to architecture](../README.md)
