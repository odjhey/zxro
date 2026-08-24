---
name: decision_v0_cli_first_python_stdlib
description: "Decision to build zxro v0.x as a dependency-free Python CLI before adding agent integrations or a compiled implementation."
type: decision
tags: [decisions, v0.x, cli, python]
status: current
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:33:00+08:00
updated_at: 2026-08-24T21:40:00+08:00
---

# 0001: Build the v0 CLI first with Python stdlib

## Context

zxro is still discovering its durable artifact and mailbox model. The first integrations are expected to be a Pi extension and Claude Code hooks, while acpx already provides persistent ACP sessions. Building around those integrations too early would couple zxro's core data model to harness details before the artifact contract has been exercised manually.

The core work is local control-plane code: validated paths, JSON records, file locking, atomic creation and replacement, CLI parsing, and subprocess-oriented tests.

## Options considered

### Python 3.11+ standard library

Build the CLI with `argparse`, `pathlib`, `json`, `fcntl`, `os`, `uuid`, `subprocess`, `tempfile`, and `unittest`. Keep integration code outside the Python package and call the CLI.

### TypeScript

Use Node/TypeScript for the core, which would align with Pi extensions and make a later `acpx/runtime` integration direct. This would add package-manager and build/tooling choices before zxro has proved that it should own agent execution at all.

### Go now

Start with a compiled single binary and stronger cross-platform process/file primitives. This would optimize the implementation before the CLI and artifact model have matured.

## Choice

Build zxro v0.x as a Python 3.11+ standard-library-only CLI.

The CLI and durable artifact shapes are the product contract. Pi, Claude, CI, humans, and future integrations call documented commands rather than importing zxro internals.

Do not embed acpx or add harness-specific integration until the manual durable artifact loop is stable.

## Consequences

- A checkout can run the core CLI and tests without installing Python packages.
- macOS/Linux are the initial platforms because v0.x uses `fcntl` locking.
- The implementation can reuse straightforward filesystem durability patterns.
- Pi integration remains a small TypeScript extension because that is Pi's native extension environment.
- Claude integration remains a command hook that invokes the zxro CLI.
- A future Go, Rust, or TypeScript rewrite remains possible if the CLI and artifact contracts stay independent from Python module APIs.
- `acpx/runtime` is deferred. If zxro later takes responsibility for agent execution, TypeScript becomes worth reevaluating.

## M1 storage refinement

M1 uses immutable per-generation JSON records plus direct event-ID and per-watchtower indexes instead of one append-only JSONL stream. This remains a Python standard-library file provider, but it makes three-record publication resumable and keeps mailbox access independent of historical event count.

## Rule or follow-up

Before adding a runtime, database, daemon, third-party Python package, or embedded agent SDK, show the concrete v0.x requirement that the dependency-free CLI cannot meet.

Every integration action must remain reproducible as a documented zxro CLI command.

## Related

- [Technology stack](../v0.x/scope/technology-stack.md)
- [Goal and scope](../v0.x/scope/goal-and-scope.md)
- [v0.x CLI](../v0.x/surfaces/cli.md)
