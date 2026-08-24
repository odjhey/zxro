---
name: contracts_index
description: "Index and stability rules for published interfaces, events, commands, and shared domain types."
type: index
tags: [architecture, contracts]
status: current
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:13:40+08:00
---

# Contracts

Contracts define information that crosses ownership boundaries. Keep implementation details in code and behavioral intent here.

## Files

- [Conventions and primitives](./conventions.md)
- [Contract template](./contract-template.md)

Add one file per cohesive contract family.

## Stability rule

A published contract change must:

1. identify affected producers and consumers;
2. describe compatibility and migration impact;
3. update terminology and diagrams when relevant;
4. receive any required human approval before implementation.

[Back to architecture](../README.md)
