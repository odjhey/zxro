---
name: contract_conventions
description: "Shared identifier, timestamp, serialization, error, and v0.x compatibility rules."
type: contract
tags: [architecture, contracts, conventions]
status: current
generated: "pi coding agent, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: "2026-08-25T18:34:06+08:00"
---

# Contract conventions and primitives

## Identifiers

Watchtower IDs, work IDs, and artifact kinds match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. `.` and `..` are invalid. Matching is case-sensitive.

Turn IDs are lowercase UUIDv4 strings. Settlement event IDs use `evt-` followed by 32 lowercase UUIDv4 hexadecimal digits. Consumers must treat every identifier and artifact reference as opaque. Only the owning zxro component may parse one for validation or provider routing.

## Time

Durable timestamps use ISO 8601 with the local UTC offset and second precision. They record operator-facing time but never define uniqueness or mailbox order. Mailbox generation defines order within one watchtower.

## Serialization and evolution

The built-in provider writes UTF-8 JSON. Public `--json` output is one JSON value on stdout. Diagnostics use stderr.

A missing optional field means the value is absent. Writers omit absent optional values rather than emitting `null`. Durable built-in-provider records fail closed on unknown fields because an older binary cannot prove their meaning. Public JSON consumers should ignore unknown fields so additive CLI output remains compatible.

Every successful public `--json` result has the shape `{"schema_version":1,"data":...}`. `schema_version` is a positive integer for the whole public machine contract. zxro emits one version per binary and does not negotiate versions. Consumers must stop on an unknown version and ignore unknown fields inside `data`.

The following changes are additive and do not require a version bump:

- adding an optional field to an existing `data` payload;
- adding a command that uses the current envelope;
- emitting a previously omitted optional field.

The following changes require a `schema_version` bump:

- removing or renaming a field;
- changing a field's type or meaning;
- changing a documented opaque identifier or reference format in a way that breaks equality with earlier values;
- changing the envelope structure.

Promoting a provider-private field into `data` is additive, but still requires contract review.

## Errors

The CLI uses these exit classes:

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Usage or validation error |
| 3 | Missing work, turn, event, or artifact |
| 4 | Conflict or invariant violation |
| 5 | Unsafe or malformed durable state |
| 6 | Child-process failure, reserved for `turn run` |

A command must diagnose the error on stderr and leave JSON stdout empty. Malformed JSON, impossible links, unexpected fields, unsafe permissions, and symlinks in managed state fail with code 5. zxro does not repair malformed state during a routine read.

## Settlement compatibility

The outcome, NFC-normalized summary, and payload digest define settlement retry equality. `source` is immutable first-write provenance, not settlement identity. A retry may omit stdin. Supplied retry bytes must match the first payload exactly. A retry cannot add payload bytes to a settlement that originally omitted them.

zxro allocates the event ID before terminal turn commit and stores it in settlement metadata. Publication assigns generation while holding the home lock. Crash-gap retries therefore retain event identity.

M1 reads M0 running records without migration and preserves all M0 command names, arguments, output fields, and exit classes. Once M1 settles a turn, an M0 binary rejects that turn's additive fields and `settled` state with code 5. Operators testing a downgrade must use a copied pre-settlement home or a fresh home. This limitation avoids unsafe lossy conversion.

## Security and privacy

Routine work, turn, and mailbox views contain bounded metadata and artifact references only. Stdin payload bytes stay in artifact storage. Built-in-provider paths must remain owned by the current user, reject symlinks, and resolve beneath the active home.

## Related

- [Contracts index](./README.md)
- [Durable store contract](./durable-store.md)
- [Ubiquitous language](../ubiquitous-language.md)
- [M1 task card](../../v0.x/execution/task-cards/m1-durable-settlement.md)
