---
name: optional_provider_evaluation_2026_08_25
description: "Evaluation of Beads and BSD mailx against the M0 and M1 durable-store contract, with adoption decisions and implementation gates."
type: report
tags: [reports, providers, storage, mailbox, v0.x]
status: draft
created_at: "2026-08-25T07:30:00+08:00"
updated_at: "2026-08-25T07:30:00+08:00"
generated: "OpenAI Codex, ADP-EVAL attempt 1, 2026-08-25"
sources:
  - ref: ../architecture/contracts/durable-store.md
    credibility: primary
  - ref: ../v0.x/execution/task-cards/m1-durable-settlement.md
    credibility: primary
  - ref: ../../tests/conformance/m1_base.py
    credibility: primary
  - ref: "local:/usr/bin/mailx and mailx(1), mail_cmds-38.0.1"
    credibility: primary
stale_after: 2027-02-25
---

# Optional provider evaluation, 2026-08-25

## Decision

Do not add either candidate as a zxro provider now.

| Candidate | Capability | Decision | Gate |
|---|---|---|---|
| Beads | Work store | Defer | An owner must provide a pinned Beads executable in a disposable namespace and approve the optional dependency. It must then pass the work-store subset of the provider conformance suite, including 12-writer testing and cleanup. |
| Beads | Mailbox | Reject | Beads is the named work-store candidate, not evidence of a mailbox implementation. Reconsider only with a documented immutable-event and independent delivery/attention model. |
| BSD `mailx` | Mailbox | Reject | Do not implement an adapter for this binary. Reconsider a different local mailbox tool only if it has deterministic non-interactive output, explicit namespace selection, stable identity, separate read and handled state, and safe concurrent publication. |
| BSD `mailx` | Work store | Reject | It has no work-item model. |

These decisions keep the built-in provider as the zero-dependency default. No candidate command or schema becomes public zxro behavior.

## Evaluation boundary

The baseline was `master` at `7a3db5acd7785bcd3946604ef2282ea887b4f7ce`. The required semantics come from the [durable-store contract](../architecture/contracts/durable-store.md) and the reusable cases named in the [M1 task card](../v0.x/execution/task-cards/m1-durable-settlement.md).

I searched `PATH` for `bd`, `beads`, `himalaya`, `notmuch`, `mu`, `meli`, `aerc`, `alot`, `mailx`, `mutt`, and `neomutt`. Only `/usr/bin/mailx` was available. I did not install a candidate or read a personal mailbox. The `mailx` checks used two temporary mbox files under `/tmp`; the command removed that directory after the checks.

A missing executable is not a failed conformance run. It means native behavior is unobserved and adoption remains gated.

## Beads evidence

Neither `bd` nor `beads` was on `PATH`. No Beads process, repository, database, or personal store was opened. Claims below are therefore limited to what this environment proved: the candidate could not be run.

| Required semantic | Native evidence | Adapter prospect | Result |
|---|---|---|---|
| Explicit namespace isolation | Not observed | Must bind every call to a disposable store without searching parent repositories or user state. | Unevaluated |
| Stable work identity and duplicate rejection | Not observed | Translation is acceptable only if native IDs and conflicts are deterministic. | Unevaluated |
| Bounded current-state reads and filtering | Not observed | The adapter may project a bounded zxro record from stable machine output. | Unevaluated |
| Turn and external-session references | Not observed | Metadata translation may supply these if round trips are lossless. | Unevaluated |
| Immutable event identity and exact lookup | Not observed | This is outside the proposed work-store role. | Fail for mailbox |
| Monotonic generation | Not observed | Adapter-owned serialization would amount to a separate mailbox store. | Fail for mailbox |
| Read ack separate from handled attention | Not observed | A work status cannot substitute for both states. | Fail for mailbox |
| Idempotent publication and crash-gap repair | Not observed | Must be proved by the M1 fault cases, not inferred from issue updates. | Unevaluated |
| Twelve concurrent settlements | Not run because the executable was absent. | Local serialization is allowed, but must preserve successful writes and deterministic conflicts. | Unevaluated |
| Deterministic machine output | Not observed | Required before parsing. Human-formatted output is not acceptable. | Unevaluated |

### Required scenario results

- Burst and 12-settlement concurrency: not run; no executable was available.
- Crash gap between terminal commit and publication: not run; no provider namespace existed.
- Ack versus handle and out-of-order handling: fail for the mailbox role because no candidate mailbox behavior was available to test.
- Isolation: not run. No repository-local initialization was attempted because it could pollute the checkout.
- Exact event lookup and idempotent retry: not run.

### Operational requirements

The executable, version, storage layout, daemon or server requirement, database format, repository files, authentication, and cleanup command are all unverified. The implementation gate requires those facts to be recorded from a pinned version. In particular, evaluation must prove that initialization does not add files to a target repository unless an owner explicitly accepts that cost.

## BSD mailx evidence

The concrete mailbox candidate was Apple's BSD `mailx`, reported by the binary as `Mail version 8.1 6/6/93`; binary provenance reports `mail_cmds-38.0.1`. It can read an explicitly named mbox with `-f`, so a disposable-file check was possible without opening the system mailbox.

The check created two mbox files, each containing two messages with explicit `Message-ID` headers. `/usr/bin/mailx -n -H -f <file>` produced a header list. A scripted `headers` and `quit` session also produced human-formatted rows. The hash of the file opened by that session then differed from its untouched copy. A nominal read can rewrite mailbox state on quit.

| Required semantic | Native behavior observed or documented | Adapter work | Result |
|---|---|---|---|
| Namespace isolation | `-f <file>` selects an alternate mbox. Startup still reads `~/.mailrc`; `-n` suppresses only system startup files. | A wrapper could set a disposable `HOME`, pass `-n`, and lock a selected file. | Partial, unsafe by default |
| Bounded reads | `-H` emits compact headers, but as human-aligned text with message numbers and byte counts. | Parsing prose and controlling startup state would be required. Message bodies would need separate reads. | Fail |
| Immutable event identity | Fixture `Message-ID` values were present in message headers, but the summary used mutable mailbox sequence numbers. | The adapter would have to parse each message and maintain its own exact index. | Fail |
| Monotonic generation | Message numbers reflect current mbox order and are not durable zxro generations. | Requires an adapter-owned durable sequence store and locking. | Fail |
| Read ack separate from handled attention | Mail flags model message state, and quitting may rewrite the mbox. No independent watchtower read cursor plus handled marker was exposed. | Requires two adapter-owned durable state sets. | Fail |
| Exact event lookup | No deterministic machine command returned one message by stable event identity with owner and generation agreement. | Requires scanning/parsing and an external direct index. | Fail |
| Idempotent publication | The receive command does not publish to an explicitly selected mbox. Sending delegates local delivery to system mail facilities. | Requires a separate safe append/delivery implementation and idempotency index. | Fail |
| Crash-gap repair | No terminal-state-to-message publication transaction or repair identity exists. | Requires the M1 publication state machine outside `mailx`. | Fail |
| Twelve concurrent settlements | Not run. `mailx` offered no direct isolated publish operation to test. Concurrent file readers/writers would need external locking. | Serialization would need to own publication, generations, and recovery. | Fail |
| Deterministic machine output | Header output is prose; version inquiry with `-V` is an illegal option. Errors and prompts share terminal-oriented behavior. | A robust adapter cannot rely on this interface without scraping prose. | Fail |
| Operational weight | The binary is preinstalled and needs no daemon or database for alternate-file reads. Safe sending depends on system mail delivery. | A wrapper would add locks, indexes, state files, startup isolation, and cleanup. | Poor fit |

### Required scenario results

- Burst: two fixture messages were listed in order, but only through mutable message numbers. This does not prove durable generation behavior.
- Crash gap: unsupported. There is no zxro terminal commit or idempotent publication boundary to repair.
- Ack versus handle: unsupported as separate durable states.
- Out-of-order handling: message flags are not an independent immutable event handled marker. The required behavior was not demonstrated.
- Isolation: alternate mbox files are selectable, but user startup configuration remains in scope unless the wrapper also replaces `HOME`. This falls short of binding all operations to one zxro home.
- Concurrency: not testable through a candidate publish API. Twelve concurrent zxro settlements would depend almost entirely on new adapter storage.
- Cleanup: delete the disposable mbox directory after all processes exit. No daemon, server, database, or authentication was used in the read check.

## Why adapter emulation does not rescue mailx

Serialization and translation are valid when they bridge a narrow mismatch. Here the adapter would need to own stable IDs, generations, exact lookup, idempotency, read cursors, handled markers, locking, publication, and crash repair. `mailx` would contribute only human-formatted mbox reads. That is another mailbox provider built beside `mailx`, not an adapter to its native semantics.

## Implementation gates

No ADP-WORK or ADP-MAIL implementation should start from this report.

A Beads work-store revisit requires all of the following:

1. owner approval for the optional executable and its storage footprint;
2. a pinned version available without modifying a personal or production store;
3. documented startup, health, namespace selection, authentication, repository effects, cleanup, and rollback;
4. deterministic machine output and stable error exits;
5. the M0 work-store cases plus 12 concurrent callers passing in disposable stores.

A mailbox revisit requires a different candidate. It must first demonstrate native stable message identity, non-interactive machine output, and explicit local namespace selection. An adapter may serialize writes or translate fields, but it must then pass every reusable M1 case, including burst reads, exact lookup, crash-gap repair, ack versus handle, out-of-order handling, isolation, bounded output, and 12 concurrent settlements.

## Related

- [Reports index](./README.md)
- [Durable-store contract](../architecture/contracts/durable-store.md)
- [Decision 0002: Separate inbox delivery position from attention handling](../decisions/0002-separate-delivery-from-attention.md)
