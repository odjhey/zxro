---
name: contracts_index
description: "Index and stability rules for published interfaces, events, commands, and shared domain types."
type: index
tags: [architecture, contracts]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T16:41:00+08:00
---

# Contracts

Contracts define information that crosses ownership boundaries. Keep implementation details in code and behavioral intent here.

## Files

- [Durable store](./durable-store.md) — provider-neutral work, turn, artifact, mailbox, ack, concurrency, and crash-recovery behavior.
- [Session binding](./session-binding.md) — durable link from one turn to an external runtime session and optional native conversation identity.
- [Agent runtime port](./agent-runtime-port.md) — semantic start/DATA/CONTROL/status/exact-resume boundary around acpx or another runtime.
- [Conventions and primitives](./conventions.md)
- [Contract template](./contract-template.md)

The durable-store contract is intentionally independent from JSON/JSONL, Beads, mail products, or any other backend. Providers and adapters may change without changing the public zxro behavior when they preserve that contract.

The runtime contracts are similarly transport-neutral. A port is a semantic interface, not a requirement for a daemon, socket, or TCP listener.

## Stability rule

A published contract change must:

1. identify affected producers and consumers;
2. describe compatibility and migration impact;
3. update terminology and diagrams when relevant;
4. receive any required human approval before implementation.

[Back to architecture](../README.md)
