---
name: optional_provider_evaluation_2026_08_25
description: "Evaluation of Beads and BSD mailx against the M0 and M1 durable-store contract, with adoption decisions and implementation gates."
type: report
tags: [reports, providers, storage, mailbox, v0.x]
status: draft
created_at: "2026-08-25T07:30:00+08:00"
updated_at: "2026-08-25T10:15:00+08:00"
generated: "OpenAI Codex, ADP-EVAL attempt 2, 2026-08-25"
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
| Beads | Work store | Defer | An owner must provide and approve a pinned Beads executable. It must pass the M0 work-store conformance subset and the applicable M1 composition tests in disposable namespaces, including 12 concurrent settlements and cleanup. |
| Beads | Mailbox | Reject as evaluated | Beads was named only as a work-store candidate. No Beads mailbox executable or behavior was available. Reconsider only if a specific version documents immutable events plus independent delivery and attention state. |
| BSD `mailx` | Mailbox | Reject | Do not implement an adapter for this binary. A different local mailbox tool needs deterministic machine output, explicit namespace selection, stable identity, independent read and handled state, and safe concurrent publication before evaluation. |
| BSD `mailx` | Work store | Reject as not applicable | `mailx` has no watchtower, work, or turn record model. |

"Reject as evaluated" does not claim that an unavailable feature failed a live test. It means the candidate, role, and evidence in this evaluation cannot meet that capability. These decisions preserve the built-in provider as the zero-dependency default. Candidate commands and schemas do not become zxro CLI behavior.

## Evaluation boundary

The baseline was `master` at `7a3db5acd7785bcd3946604ef2282ea887b4f7ce`. Required semantics come from the [durable-store contract](../architecture/contracts/durable-store.md), reusable M0/M1 conformance cases, and the [M1 task card](../v0.x/execution/task-cards/m1-durable-settlement.md).

I did not install software, initialize Beads, open a personal mailbox, change provider configuration, or touch a production namespace. Candidate checks used command discovery and two disposable mbox files under `/tmp`. The shell trap removed the directory.

The tables use these result terms:

- **Observed** means the disposable command demonstrated the behavior.
- **Specific failure** means the available native interface lacks the required operation or returned unsuitable evidence.
- **Adapter required** means an adapter could supply the behavior, subject to conformance tests.
- **Not observed, gated** means the missing executable prevented a test. It is not a conformance failure or evidence of support.
- **Not applicable** means the candidate was not proposed for that capability.

## Reproducible candidate discovery

Run from any directory. It reads `PATH` and binary metadata only.

```sh
for x in bd beads himalaya notmuch mu meli aerc alot mailx mutt neomutt; do
  if command -v "$x" >/dev/null 2>&1; then
    printf '%s\t%s\n' "$x" "$(command -v "$x")"
  fi
done
/usr/bin/mailx -V 2>&1 || true
file /usr/bin/mailx
what /usr/bin/mailx 2>/dev/null | head -20 || true
```

Observed output:

```text
mailx   /usr/bin/mailx
/usr/bin/mailx: illegal option -- V
Usage: mailx ...
/usr/bin/mailx: Mach-O universal binary with 2 architectures ...
PROGRAM:mail  PROJECT:mail_cmds-38.0.1
```

No `bd` or `beads` path was printed. The absence is reproducible for this environment but says nothing about other installations.

## Beads evaluation

Neither `bd` nor `beads` was on `PATH`. No process, repository, daemon, database, or user store was opened. Every native Beads result is therefore "Not observed, gated."

### M0 work, turn, and namespace semantics

| Required semantic or safety case | Native evidence | Adapter or gate mapping | Result |
|---|---|---|---|
| Explicit namespace selection and two-home isolation | No executable; no store initialized. | Every call must name a disposable store equivalent to `$ZXRO_HOME`. Missing-object reads must not create it or search parent repositories. | Not observed, gated |
| Watchtower create, show, list, stable ID, and duplicate rejection | No executable. | Adapter must preserve zxro IDs and return deterministic conflicts without overwrite. | Not observed, gated |
| Work create, show, list, filters, close, and history retention | No executable. | Machine output must support watchtower/state filtering. Close must preserve turns and history. | Not observed, gated |
| Bounded work reads after long turn history | No executable. | Projection may translate native records, but output and read cost must not grow with artifact bodies or handled history. | Not observed, gated |
| Turn create, show, list, lifecycle, and identity separation | No executable. | Adapter must keep work, turn, runtime session, native session, and cwd distinct and round-trip external references. | Not observed, gated |
| Missing watchtower, work, turn, and namespace behavior | No executable. | Unknown reads and parents must fail without creating files, records, repositories, or databases. | Not observed, gated |
| Deterministic machine output and errors | No executable. | Require structured output, stderr diagnostics, stable nonzero exits, and non-interactive operation from a pinned version. | Not observed, gated |

### M1 settlement, artifact, and mailbox semantics

Beads remains only a possible work store. A composed provider must still satisfy every row; delegation to the built-in turn, artifact, or mailbox provider is acceptable if composition preserves settlement ordering.

| Required semantic or safety case | Native evidence | Adapter or composition mapping | Result |
|---|---|---|---|
| Terminal outcomes `completed`, `failed`, `cancelled` and conflicting status rejection | No executable. | Turn provider must accept only supported outcomes, normalize the summary, and reject a conflicting terminal result deterministically. | Not observed, gated |
| Settlement idempotency and stable event identity | No executable. | Retry of equal outcome, summary, and payload digest must return the original settlement and event ID without another generation. | Not observed, gated |
| Immutable event, exact event-ID lookup, and owner/generation agreement | No mailbox candidate behavior. | A separate mailbox provider must own immutable envelopes and a direct exact index. A Beads work status cannot stand in for this index. | Adapter required for composition |
| Monotonic integer generation and burst delivery | No mailbox candidate behavior. | Mailbox provider must assign unique per-watchtower generations and return only generations after durable ack. | Adapter required for composition |
| Read ack integrity | No mailbox candidate behavior. | Ack must reject booleans, strings, floats, missing generations, mismatched indexes, backwards movement, and values above high-water before mutation. | Adapter required for composition |
| Read ack separate from handled attention | No mailbox candidate behavior. | A separate cursor and per-event handled state must keep acknowledged but unhandled events pending. | Adapter required for composition |
| Out-of-order and idempotent handling | No mailbox candidate behavior. | Exact handling must support later events first, preserve immutable history, and make duplicate handle calls converge. | Adapter required for composition |
| Handle crash recovery | No mailbox candidate behavior. | Authoritative handled state must commit before unresolved-index removal. Faults around both writes must leave pending or durably handled state. | Adapter required for composition |
| Artifact put, metadata, explicit resolve, and traversal safety | No executable. | Artifact provider must keep payload bytes out of work, turn, unread, and pending output; references need byte/digest metadata and namespace-safe resolution. | Not observed, gated |
| Fail-closed cross-record reads | No executable. | Unread and pending must reject missing or mismatched terminal turns, ownership, settlement identity, outcome, summary, direct index, and artifact metadata. | Not observed, gated |
| Crash gap after terminal commit | No executable. | Composition must allocate event ID before terminal commit, resume publication with that ID, and never expose an event before its turn and artifact metadata. | Not observed, gated |
| Idempotent publication and partial-publication repair | No executable. | Retries must reconcile event, direct index, high-water, and unresolved state without overwrite or duplicate generation. | Not observed, gated |
| Missing-object behavior | No executable. | Missing artifact, event, generation, ack target, and handle target must fail without unrelated mutation or namespace creation. | Not observed, gated |
| Bounded history and progressive disclosure | No executable. | Empty unread/pending and one new settlement must not scan handled history; pending scales with unresolved bounded envelopes, not artifact bytes. | Not observed, gated |
| Twelve concurrent settlements | No executable. | Native locking or adapter serialization must preserve every successful write, unique ordered generations, stable IDs, and deterministic conflicts. | Not observed, gated |

### Required scenario and operational results

Burst, crash-gap, out-of-order handling, isolation, and 12-settlement concurrency were not run because there was no executable or disposable namespace. Ack integrity, handle recovery, bounded history, and missing-object checks were also not run. Their required mappings appear above so absence cannot be mistaken for support.

The version, daemon/server requirement, database and storage layout, external binaries, repository pollution, authentication, startup/health commands, cleanup, and rollback are unknown. A revisit must record each item from a pinned version. Initialization must occur outside the target checkout unless an owner explicitly accepts repository files.

## Disposable BSD mailx check

The concrete local mailbox candidate was Apple's BSD `mailx`. It reports `Mail version 8.1 6/6/93`, while binary provenance reports `mail_cmds-38.0.1`.

The complete fixture and command sequence follows. It writes only beneath a new `/tmp` directory. `-f` avoids the system mailbox, `-n` skips system startup files, and `HOME="$TMP/home"` prevents use of the personal `~/.mailrc`.

```sh
set -eu
TMP=$(mktemp -d /tmp/zxro-mailx-eval.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
mkdir "$TMP/home"
cat >"$TMP/a.mbox" <<'EOF'
From sender@example.test Tue Aug 25 00:00:00 2026
Message-ID: <evt-a@example.test>
Date: Tue, 25 Aug 2026 00:00:00 +0000
From: sender@example.test
To: main@example.test
Subject: first

body-a

From sender@example.test Tue Aug 25 00:00:01 2026
Message-ID: <evt-b@example.test>
Date: Tue, 25 Aug 2026 00:00:01 +0000
From: sender@example.test
To: main@example.test
Subject: second

body-b
EOF
cp "$TMP/a.mbox" "$TMP/b.mbox"
HOME="$TMP/home" /usr/bin/mailx -n -H -f "$TMP/a.mbox" 2>&1
printf 'headers\nquit\n' |
  HOME="$TMP/home" /usr/bin/mailx -n -N -f "$TMP/a.mbox" 2>&1
shasum -a 256 "$TMP/a.mbox" "$TMP/b.mbox"
find "$TMP" -maxdepth 2 -type f -print | sort
```

Material output from the evaluation run:

```text
Mail version 8.1 6/6/93.  Type ? for help.
"/tmp/zxro-mailx-eval.../a.mbox": 2 messages 2 new
>N  1 sender@example.test   Tue Aug 25 00:00   9/193   "first"
 N  2 sender@example.test   Tue Aug 25 00:00   8/193   "second"
>N  1 sender@example.test   Tue Aug 25 00:00   9/193   "first"
 N  2 sender@example.test   Tue Aug 25 00:00   8/193   "second"
"/tmp/zxro-mailx-eval.../a.mbox" complete
f35a1666...  .../a.mbox
7b81c7d5...  .../b.mbox
.../a.mbox
.../b.mbox
```

The differing hashes show that the scripted receive session rewrote the selected mailbox while its untouched copy retained the fixture bytes. The output is terminal-oriented prose. It exposes mutable message numbers, not a stable machine event identity.

## BSD mailx semantic matrix

### Mailbox semantics and safety

| Required semantic or safety case | Observed evidence or specific failure | Adapter mapping | Result |
|---|---|---|---|
| Namespace isolation | Observed: `-f` selected a disposable mbox. Personal startup state is avoided only by replacing `HOME`; `-n` alone skips system files, not `~/.mailrc`. | Wrapper must bind `HOME`, `-n`, file path, and locks to one zxro home. | Partial native behavior |
| Bounded machine reads | `-H` listed two bounded headers, but as human-aligned prose. It did not provide structured fields or stable parsing. | Parser would scrape prose; body separation alone is insufficient. | Specific failure |
| Immutable event identity | Fixture `Message-ID` headers existed in bodies, while summary rows exposed mailbox sequence numbers. No immutable zxro envelope was returned. | Requires message parsing plus adapter-owned immutable records. | Specific failure |
| Exact event lookup | No non-interactive machine command returned one message by event ID with owner and generation agreement. | Requires a separate direct index and validation. | Specific failure |
| Monotonic integer generation | Displayed numbers represent current mbox positions and may change after mailbox rewrite. | Requires adapter-owned sequence allocation and locking. | Specific failure |
| Idempotent publication | Receive mode cannot publish to the selected mbox. Send mode delegates delivery to system mail facilities and has no idempotency key. | Requires separate append/delivery and idempotency storage. | Specific failure |
| Settlement/status/idempotency | `mailx` has no turn terminal-state operation or supported zxro outcome model. | Turn provider must own status validation, terminal conflict, digest equality, and stable settlement identity. | Adapter required for composition |
| Crash-gap and partial-publication repair | No transaction relates a turn commit to mbox delivery, direct index, high-water, or unresolved state. | Requires the full M1 publication state machine outside `mailx`. | Specific failure |
| Ack integrity | Message flags are not an integer read cursor. No operation validates every generation before monotonic cursor advance. | Requires adapter-owned cursor, exact generation validation, and fail-before-mutation behavior. | Specific failure |
| Ack separate from handled attention | No independent cursor plus durable per-event handled marker exists. The receive session can rewrite message state on quit. | Requires two adapter-owned state models. | Specific failure |
| Out-of-order idempotent handle | Message mutation/deletion does not preserve an immutable event with independent handled state. | Requires exact adapter markers and unresolved index. | Specific failure |
| Handle recovery | No authoritative handled-marker-first protocol or retry repair operation exists. | Requires fault-safe state outside `mailx`. | Specific failure |
| Artifact handling | Bodies can be fetched separately in an interactive session, but there is no opaque artifact reference, metadata record, digest check, or namespace-safe resolve operation. | Requires a separate artifact provider. | Specific failure |
| Fail-closed cross-record reads | No linked turn, settlement, direct index, artifact metadata, or owner records exist to validate. | Requires the complete cross-record validation layer. | Specific failure |
| Missing-object behavior | Missing alternate files and message numbers use mail-oriented errors, not provider-neutral errors; safe no-create behavior was not established for every operation. | Requires stable errors and tests proving no namespace or unrelated mutation. | Not demonstrated |
| Bounded handled history | Header output is bounded per message, but unread/pending views and handled-history-independent read cost do not exist. | Requires separate high-water and unresolved indexes. | Specific failure |
| Burst delivery | Observed only that two fixture messages were listed in file order with mutable numbers. This does not prove delta-only unread or durable generations. | Requires generation/index storage and burst conformance. | Partial, nonconforming evidence |
| Twelve concurrent settlements | Not run because there is no isolated publish API. Concurrent mbox publication would depend on external locking and delivery behavior. | Adapter would own serialization, generation, repair, and conflict handling. | Not demonstrated |
| Deterministic machine interface | `-V` is illegal; headers and prompts are prose. | A stable adapter must not scrape this output. | Specific failure |

### M0 work and turn semantics

BSD `mailx` has no watchtower, work, turn, lifecycle, close, filter, cwd, session, or native-session record. Stable work IDs, duplicate rejection, bounded current state, identity separation, and missing-parent behavior are therefore not applicable to the mailbox role and specifically absent for a work-store role. Composition would retain another provider for all M0 records.

### Operational requirements

| Requirement | Finding |
|---|---|
| Daemon or server | None for alternate-file reads. Sending depends on local system mail delivery. |
| Database | None. The selected mbox file is mutable storage. |
| External binary | `/usr/bin/mailx`, `mail_cmds-38.0.1`; behavior is platform-specific. |
| Repository pollution | None in the disposable check. A poorly selected `HOME` or mbox path could affect user state. |
| Authentication | None for local reads. Delivery configuration and remote mail were not tested. |
| Startup/configuration | Safe evaluation required `HOME=<disposable>`, `-n`, and explicit `-f <disposable mbox>`. |
| Cleanup | Wait for the process, then remove the disposable directory. The shell trap performed this step. |
| Concurrency/locking | No suitable publication operation was available. External locking would be required and remains unproved. |
| Operational weight | The reader binary is preinstalled, but a conforming adapter would add locks, indexes, artifact state, cursor state, handled state, and repair logic. |

## Why adapter emulation does not rescue mailx

Serialization and translation are valid for narrow mismatches. Here an adapter would own stable IDs, generations, exact lookup, settlement idempotency, read cursors, handled markers, artifact metadata, locking, publication, fail-closed validation, and crash repair. `mailx` would contribute only terminal-formatted mbox reads. That is a new mailbox provider beside `mailx`, not a useful adapter to native behavior.

## Implementation gates

No ADP-WORK or ADP-MAIL implementation should start from this report.

A Beads work-store revisit requires:

1. explicit owner approval for the optional executable and storage footprint;
2. a pinned version in a disposable namespace, without personal or production state;
3. documented daemon, server, database, binary, repository, authentication, startup, health, cleanup, and rollback requirements;
4. deterministic structured output, stable IDs, and stable nonzero errors;
5. every M0 work-store row above passing reusable conformance tests;
6. composed M1 settlement, artifact, fail-closed, isolation, bounded-history, and 12-concurrent-settlement tests passing.

A mailbox revisit requires a different concrete candidate. Before adapter work, it must demonstrate native stable message identity, non-interactive machine output, and explicit local namespace selection. The complete M1 suite must then prove status and retry equality, artifacts, exact lookup, ack integrity, independent handling, handle recovery, missing-object behavior, bounded history, burst delivery, crash repair, out-of-order handling, isolation, and 12 concurrent settlements.

## Related

- [Reports index](./README.md)
- [Durable-store contract](../architecture/contracts/durable-store.md)
- [Decision 0002: Separate inbox delivery position from attention handling](../decisions/0002-separate-delivery-from-attention.md)
