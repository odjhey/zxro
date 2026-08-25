---
name: a1_versioned_json_envelope_task_card
description: "Task card for wrapping all public --json output in the schema_version envelope and publishing the bump-versus-additive compatibility policy."
type: checklist
tags: [v0.x, execution, task-cards, cli, json]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
created_at: "2026-08-25T14:25:09+08:00"
updated_at: "2026-08-25T14:25:09+08:00"
---

# A1 — Versioned JSON envelope

Implements WP1 of the [machine contract design](../machine-contract-design.md) (issue #25).

## Outcome

Every `zxro --json` response on stdout is `{"schema_version": 1, "data": ...}` for both object and list payloads, output stays byte-deterministic, and the bump-versus-additive compatibility policy is published in [contract conventions](../../../architecture/contracts/conventions.md) as current behavior.

## Inputs and dependencies

- No card blocks this one. First card in lane A; [A2](./a2-namespaced-work-metadata.md) stacks on it.
- Runs in parallel with lanes B, C, and D. This card rewrites every `--json` test assertion, so it is the main cross-lane conflict source: cards B1, C1, C2, and D1 must assert JSON shapes through a shared test helper that unwraps the envelope when present, so they pass whether they merge before or after A1.

## In scope

- Envelope wrapping at the single machine-output point in `zxro/cli.py` (`render()` or a dedicated function), preserving `sort_keys=True` and compact separators.
- Promoting the design's D2 bump rules into contract conventions, replacing the placeholder paragraph that says no version exists yet.
- Updating the CLI spec's global behavior section from "planned" to current.
- Sweeping tests, task cards, the Web UI plan, and playbooks for bare `--json` shape assumptions.
- Black-box tests pinning the envelope for `watchtower show`, `work show`, `work list`, `turn create`, `turn settle`, `inbox unread`, `inbox pending`, `ack`, and `artifact path`.
- Error-path tests proving stdout stays empty in `--json` mode for exit classes 2, 3, 4, and 5.

## Out of scope

- Work metadata (card [A2](./a2-namespaced-work-metadata.md)).
- A machine-readable error envelope (recorded as rejected for v0.x in the design).
- Version negotiation flags; one binary emits one version.

## Contract

| Produces | Consumes | Must not change |
|---|---|---|
| Enveloped `--json` output for every command; published compatibility policy; envelope-tolerant test helper | `zxro/cli.py` machine-output path; design D1 and D2 | Human-readable output; exit classes; stderr diagnostics; determinism of repeated reads |

## Steps

1. Add the envelope at the machine-output point; confirm no command bypasses it.
2. Add the shared test helper that accepts enveloped output, and convert existing `--json` assertions to it.
3. Add the representative wire-shape tests and error-path stdout tests.
4. Update contract conventions, the CLI spec, and any doc that showed bare `--json` payloads.

## Acceptance criteria

- [ ] All public `--json` responses carry `schema_version` with identical convention for objects and lists.
- [ ] Repeating a read command produces byte-identical output.
- [ ] Error paths leave stdout empty; exit classes are unchanged.
- [ ] Bump-versus-additive rules are published in contract conventions as current behavior.
- [ ] No doc or test still presents bare `--json` payloads as current.

## Verification

```sh
python3 -m unittest discover -s tests -v
ZXRO_HOME=$(mktemp -d) sh -c 'bin/zxro watchtower create w --cwd /tmp && bin/zxro --json watchtower show w | python3 -c "import json,sys; d=json.load(sys.stdin); assert d[\"schema_version\"]==1 and \"data\" in d"'
```

## Documentation impact

- [ ] Contract conventions carry the compatibility policy; CLI spec global behavior updated.
- [ ] Machine contract design WP1 marked delivered; indexes untouched (no new docs).

## Human gate

Contract compatibility review required by the [contracts index](../../../architecture/contracts/README.md); this change deliberately breaks any existing bare-payload consumer.

## Related

- [Machine contract design](../machine-contract-design.md)
- [Task-card index](./README.md)
