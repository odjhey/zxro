---
name: v0x_machine_contract_design
description: "Implementation-ready design for the versioned public JSON envelope and namespaced work metadata: wire shapes, bump rules, bounds, validation, CLI commands, work packages, and test mapping for issues #25 and #26."
type: plan
tags: [v0.x, execution, cli, json, metadata, contracts]
status: draft
generated: "Claude Fable 5 agent, 2026-08-25"
sources:
  - ref: https://github.com/odjhey/zxro/issues/25
    credibility: primary
  - ref: https://github.com/odjhey/zxro/issues/26
    credibility: primary
  - ref: ../../architecture/contracts/conventions.md
    credibility: primary
  - ref: ../../architecture/contracts/durable-store.md
    credibility: primary
created_at: "2026-08-25T13:00:51+08:00"
updated_at: "2026-08-25T18:34:06+08:00"
---

# Machine contract design: versioned JSON envelope and namespaced metadata

## Purpose

This design resolves issue #25 (version the machine JSON contract) and issue #26 (namespaced optional metadata and external references) into two implementable work packages. A developer should be able to build either package from this document plus the linked contracts without re-deriving the decisions.

The envelope must land first. Metadata is exposed through `--json` output, so its wire shape should never exist unversioned.

## Current state

- `zxro --json` prints one compact JSON value on stdout (`sort_keys=True`, separators `(",", ":")`) with no schema identifier. See `zxro/cli.py` `render()`.
- Object commands print one JSON object; list commands print one JSON array. `artifact path --json` prints `{"path": ...}`.
- Diagnostics go to stderr; exit classes are defined in [contract conventions](../../architecture/contracts/conventions.md#errors).
- The [durable store contract](../../architecture/contracts/durable-store.md) already reserves `work.create(id, watchtower_id, metadata?)` but nothing persists or exposes metadata today.
- Durable built-in-provider records fail closed on unknown fields; public JSON consumers ignore unknown fields.

## Decisions

### D1: One envelope for all public `--json` output

Every `--json` response wraps its payload:

```json
{
  "schema_version": 1,
  "data": {}
}
```

List commands wrap the array the same way:

```json
{
  "schema_version": 1,
  "data": [{}, {}]
}
```

Rules:

- `schema_version` is a positive integer describing the whole public machine contract, not per-command versions. One number is enough at this size, and consumers get one switch to branch on.
- The envelope applies to every command's `--json` form, including `turn create`, `artifact path`, `ack`, and `inbox handle`. No command keeps a bare payload.
- Human-readable output is unchanged.
- Errors keep the existing behavior: stdout stays empty, diagnostics on stderr, exit classes unchanged. v0.x does not add a machine-readable error envelope; a caller that needs error detail parses the exit class. Recording this as a decision avoids half-versioned error objects later.
- Output stays deterministic: `sort_keys=True` and compact separators are preserved, so `data` sorts before `schema_version` and byte-identical inputs keep producing byte-identical outputs.

### D2: Bump rules

The compatibility policy below moves into [contract conventions](../../architecture/contracts/conventions.md) verbatim when work package 1 lands.

Additive, no bump required:

- adding a new optional field to an existing `data` payload;
- adding a new command whose `--json` output uses the current envelope;
- emitting a previously omitted optional field.

Requires a `schema_version` bump:

- removing or renaming a field;
- changing a field's type or meaning;
- changing identifier or reference formats consumers were told to treat as opaque in a way that breaks equality with previously emitted values;
- changing envelope structure itself.

Consumers must ignore unknown fields inside `data`. A consumer that receives an unknown `schema_version` should stop rather than guess. zxro v0.x emits exactly one version per binary; there is no negotiation flag.

Provider-private schemas stay private. Promoting a provider field into `data` is an additive contract change and needs the same review as any contract edit.

### D3: Namespaced metadata on work records

Work records gain one optional `metadata` field: a JSON object whose top-level keys are namespaces and whose values are namespace-owned JSON objects.

```json
{
  "id": "auth-fix",
  "watchtower_id": "main",
  "state": "open",
  "metadata": {
    "beads": {
      "issue_id": "bd-a19f"
    },
    "github": {
      "issue": 96
    }
  }
}
```

- Only work records carry metadata in this milestone. Watchtower, turn, and artifact metadata are deferred until a consumer needs them; the validation and bounds below are written to be reusable when that happens.
- There is no typed top-level external-reference structure in v0.x. Opaque namespaces already satisfy issue #26's acceptance, and a typed structure would force zxro to pick which sibling systems are first-class. Revisit only when two or more real integrations need cross-namespace queries.
- zxro core never interprets a namespace's contents. Namespace payloads round-trip byte-equivalently (modulo canonical JSON re-serialization) through create, show, list, close, and settlement of related turns.
- The namespace `zxro` is reserved and rejected on write.

### D4: Bounds and validation

Metadata must stay routing-sized. The bounds:

| Bound | Value |
|---|---|
| Namespace key | matches `[a-z0-9][a-z0-9._-]{0,63}`, no `.` or `..` |
| Keys inside a namespace | same pattern as namespace keys |
| Nesting depth inside a namespace value | at most 4 |
| String value length | at most 2,048 Unicode characters after NFC normalization |
| Total serialized `metadata` per record | at most 16 KiB UTF-8 |
| Value types | object, string, integer, boolean; no floats, no nulls, arrays of the allowed scalar types only |

Violations fail with exit class 2 before any durable write. Malformed durable metadata found on read fails closed with exit class 5, matching existing unsafe-state behavior. There is no partial acceptance and no silent truncation.

Floats are excluded because deterministic re-serialization of floats across Python versions is not worth proving for reference-style metadata. Nulls are excluded because [contract conventions](../../architecture/contracts/conventions.md#serialization-and-evolution) already define absence as omission.

Progressive disclosure holds: 16 KiB is deliberately too small for reports, transcripts, or artifact bodies. Anything larger belongs in an artifact and gets referenced by its ID.

Secrets: zxro cannot reliably detect credentials in opaque values, so enforcement is policy plus review, not scanning. The CLI documentation must state that metadata is durable, unencrypted, and readable by anything that can read `$ZXRO_HOME`, and that tokens and credentials are forbidden. Recording detection as out of scope is part of this decision.

### D5: Metadata CLI commands

Namespace-granular replace keeps concurrency semantics simple: the unit of write is one whole namespace, serialized under the existing home lock, last writer wins per namespace, no JSON patch language.

```sh
zxro work meta set auth-fix beads --stdin
zxro work meta set auth-fix github --stdin
zxro work meta show auth-fix
zxro work meta show auth-fix beads
zxro work meta unset auth-fix beads
```

- `set` reads one JSON object for the named namespace from stdin, validates it against D4, and replaces that namespace atomically. Other namespaces are untouched.
- `show` without a namespace prints all metadata; with a namespace, that namespace's object. `--json` forms use the D1 envelope.
- `unset` removes one namespace. Removing a missing namespace is idempotent success.
- Metadata edits are allowed on closed work. Linking a tracker issue after close is a normal operation and does not reopen the work item.
- Metadata never changes work identity, state, lifecycle, mailbox behavior, or settlement identity.

External references use stable identifiers supplied by the caller (a Beads issue ID, a GitHub issue number). zxro must not derive or infer them from cwd, process, or session identity.

### D6: Compatibility fallout

- Adding `metadata` to work `--json` output is additive under D2; no bump. Work package 1 and 2 both ship inside `schema_version: 1`.
- An older binary reading a durable work record that carries `metadata` rejects it with exit class 5, the same fail-closed downgrade posture the M0/M1 boundary already documents in [contract conventions](../../architecture/contracts/conventions.md#settlement-compatibility). Operators who need a downgrade path use a copied home, as before.
- The envelope itself is a breaking change for any current `--json` consumer. That is the point of doing it now, before external consumers exist. The task cards in this repo and the Web UI plan's read contracts must be swept for bare-payload assumptions in work package 1.

## Work packages

### WP1: versioned envelope

Status: implemented, pending the contract compatibility merge gate.

Outcome: every `zxro --json` response is `{"schema_version": 1, "data": ...}`, and the compatibility policy is published in the contract docs.

Steps:

1. Wrap machine output in `render()` (or a dedicated envelope function) so every `--json` path emits the envelope; keep `sort_keys` and compact separators.
2. Sweep existing tests, task cards, the Web UI plan, and playbooks for bare `--json` shape assumptions; update them.
3. Move the D2 bump rules into [contract conventions](../../architecture/contracts/conventions.md) as current behavior and update the CLI spec's global behavior section.
4. Add black-box tests pinning the versioned wire shape for at least: `watchtower show`, `work show`, `work list` (object and list forms), `turn create`, `turn settle`, `inbox unread`, `inbox pending`, `ack`, `artifact path`.
5. Verify error paths leave stdout empty in `--json` mode for exit classes 2, 3, 4, and 5.

Acceptance (maps to issue #25):

- [ ] All public `--json` responses carry `schema_version`.
- [ ] Object and list responses use the same envelope convention.
- [ ] Bump-versus-additive rules are documented in contract conventions.
- [ ] Black-box tests pin envelope presence and representative payload shapes.
- [ ] Determinism and exit behavior are unchanged; stdout remains machine-only.

### WP2: namespaced work metadata

Outcome: work records store and expose bounded namespaced metadata through the versioned contract; depends on WP1.

Steps:

1. Implement D4 validation as a reusable function with exhaustive deterministic error messages.
2. Persist `metadata` on work records in the built-in provider; absent means omitted, never `null`.
3. Implement `work meta set|show|unset` per D5, serialized under the home lock.
4. Include `metadata` in `work show` and `work list` output, human and `--json` forms; keep list output one line per work item in human form by summarizing to namespace names.
5. Extend the durable-store conformance suite: round-trip through create, meta set, close, turn settle; namespace isolation between two namespaces and between two homes; bounds enforcement at each limit; malformed input at exit class 2; malformed durable state at exit class 5; idempotent unset; reserved `zxro` namespace rejection.
6. Update the durable store contract's work object and `work.update` sections and the CLI spec.

Acceptance (maps to issue #26):

- [ ] Work records store and return bounded namespaced metadata.
- [ ] Metadata survives lifecycle operations unchanged unless explicitly updated.
- [ ] JSON output exposes metadata through the D1 envelope.
- [ ] Tests cover namespace isolation, validation, round-trip, bounds, and malformed input.
- [ ] Core behavior stays provider-neutral; no provider-specific interpretation in core.

## Verification

```sh
python3 -m unittest discover tests
zxro --json work show <id>   # envelope present, deterministic bytes on repeat
```

## Human gate

Both packages edit published contract documents, so each PR needs the explicit compatibility review that the [contracts index](../../architecture/contracts/README.md) requires. No other gate.

## Related

- [Contract conventions](../../architecture/contracts/conventions.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [v0.x CLI](../surfaces/cli.md)
- [CLI-first delivery plan](./cli-first-delivery-plan.md)
- [Execution index](./README.md)
