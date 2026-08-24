---
name: system_context_diagram
description: "Starter Mermaid diagram for the system boundary, actors, and external dependencies."
type: diagram
tags: [architecture, diagrams, mermaid]
status: draft
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
---

# System Context

```mermaid
flowchart LR
    User[User or operator] --> System[Product system]
    System --> External[External dependency]
```

Replace the placeholders once system boundaries are known.

## Related

- [Product architecture](../product-architecture.md)
- [Diagrams index](./README.md)
