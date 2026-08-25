---
name: v0x_surfaces_index
description: "Index for user-facing, operator-facing, and machine-facing v0.x interfaces."
type: index
tags: [v0.x, surfaces]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-25T09:00:00+08:00
---

# v0.x surfaces

The CLI is the first product interface. It must be useful by hand before Pi or Claude integrations automate the same commands.

- [v0.x CLI](./cli.md) covers current durable CRUD, settlement, mailbox, acknowledgement, and artifact resolution. It also records unavailable future M2 inspection and metadata helpers.
- [Surface template](./surface-template.md) — starting point for a later interface spec.

Routine CLI reads return bounded summaries, metadata, and references. They do not inline accumulated reports or logs.

[Back to v0.x](../README.md)
