---
name: decisions_index
description: "Convention and index for durable zxro architecture, product, and operating decisions."
type: index
tags: [decisions]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T21:40:00+08:00
---

# Decision records

Use decision records for choices whose rationale or consequences future contributors need to understand.

## Naming

`NNNN-short-kebab-title.md`, using the next available number.

## Required sections

- Context
- Options considered
- Choice
- Consequences
- Rule or follow-up

## Accepted decisions

- [0001: Build the v0 CLI first with Python stdlib](./0001-v0-cli-first-python-stdlib.md)
- [0002: Separate inbox delivery position from attention handling](./0002-separate-delivery-from-attention.md)

Start from [0000-template.md](./0000-template.md). Add accepted records to this index and to [docs/INDEX.md](../INDEX.md). Mark replaced records `superseded` and link their replacement.
