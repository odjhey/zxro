---
name: v0x_cli_first_web_ui_plan
description: "Implementation plan for a local, view-only Web UI that reads ZXRO durable state through the merged public CLI and records the read-contract gaps needed for parity and later analysis."
type: plan
tags: [v0.x, execution, cli, web-ui, operator]
status: draft
generated: "OpenAI GPT-5.4, 2026-08-25"
sources:
  - ref: ../../architecture/contracts/durable-store.md
    credibility: primary
  - ref: ../surfaces/cli.md
    credibility: primary
  - ref: ../validation/cli-multiturn-operator-readiness.md
    credibility: primary
  - ref: ../../../zxro/cli.py
    credibility: primary
  - ref: ../../../zxro/localfs/durable.py
    credibility: primary
  - ref: ../../../tests/test_cli_multiturn.py
    credibility: primary
  - ref: ../../../tests/test_cli_global.py
    credibility: primary
  - ref: ../engineering/runtime-and-provisioning.md
    credibility: primary
created_at: "2026-08-25T09:35:45+08:00"
updated_at: "2026-08-25T10:12:39+08:00"
---

# CLI-first Web UI plan

## Plan provenance

- `attempt_count: 6`
- `caused_by: independent reviewer detailed G19/G6, refresh and logging contract defects; separate scout verified M2 env/bind/run wording inconsistency`
- Baseline: merged `origin/master` at `a191ae7`, including M0, M1, and the public-CLI multi-turn readiness evidence.
- Verification during planning: `python3 -m unittest discover -s tests -v` passed 84 of 84 tests against that baseline.

This plan concerns ZXRO. Rozoro is relevant only as prior operational evidence already cited by ZXRO's architecture documents.

## Decision

Build the first Web UI as a local, one-home, view-only projection of the public ZXRO CLI. The UI must invoke stable `--json` commands. It must not import `zxro.localfs`, walk `$ZXRO_HOME`, parse provider files, invoke provider commands, or maintain a second ZXRO domain implementation.

The merged CLI is authoritative, but two commands that look like reads are not physically read-only:

- `inbox pending` may compact unresolved state and therefore takes the mutation path.
- `artifact path` may create a `.bin` materialization and therefore takes the mutation path.

The UI must not call either command until the core CLI offers provider-neutral, physically read-only equivalents. This is the first parity gate. It is not permission to bypass the CLI.

A Web UI can then make existing state easier to inspect, search, and compare. It cannot recover facts that ZXRO does not persist. Decisions, prompt text and versions, causal links, attempt ordinals, retry failures, work timestamps, and running-turn start times are absent from merged M0/M1 state. The UI must label those questions unavailable instead of inferring answers from names or prose.

## Baseline and delivery boundaries

### Merged now

M0 and M1 provide these public commands:

```text
watchtower create|show|list
work create|show|list|close
turn create|show|list|settle
inbox unread|pending|handle
ack
artifact path
```

The Web UI may use only approved read invocations. Mutation commands remain outside its executable command allowlist even when their successful output contains useful records.

The built-in local provider currently stores watchtowers, work, turns, artifacts, immutable mailbox events, direct event indexes, mailbox acknowledgement and unresolved state, and handled markers. That layout is private. It is evidence for proposed read contracts, not a UI integration point.

### Unavailable or deferred

The following are not merged and must not appear as working UI features:

- M2 `inspect` and read-only `turn env`;
- M2 mutating, idempotent `turn bind` enrichment;
- child-launching `turn run`, deferred separately beyond M2;
- optional Beads or mailbox adapters;
- Pi or Claude completion producers;
- M7 watchtower wake, prioritization, routing, or dispatch automation;
- hosted or remote ZXRO operation.

M2 work on other branches does not change this baseline. This Web UI plan does not implement issue #12 or depend on it. All four commands are unavailable on `master`, and none is a Web UI operation. A future UI may consume bounded `inspect --json` output after parity and purity review; the MVP simply does not depend on it. `turn env` would only format `ZXRO_*` metadata, `turn bind` would mutate a turn's late native-session provenance, and `turn run` would launch a child process beyond M2.

### Frozen provider posture

The built-in provider is the only merged provider. The optional-provider evaluation deferred Beads and rejected the evaluated BSD `mailx` roles. No Web UI milestone may revive those adapters, depend on provider-native schemas, or treat an unmerged adapter branch as evidence. A future adapter must first satisfy the durable-store conformance suite and the read contracts proposed here.

## Logging and observability audit

The merged CLI has error reporting, not a logging system:

- `zxro.cli.main` prints one human-readable error line to stderr for `ZxroError` and `OSError` failures.
- Stable exit classes 2 through 5 distinguish validation, missing, conflict, and unsafe state.
- `--json` keeps successful stdout machine-readable. Tests require empty stderr on success and non-empty stderr on failure.
- Public show, list, unread, pending, and artifact commands provide local diagnostic evidence.
- The runtime guide explicitly says v0.x has no metrics, traces, network health endpoint, or background health checks.

No merged module defines structured diagnostic events, event names, a log schema, levels, correlation IDs, performance timings, retention, rotation, or redaction. The CLI does not record command starts, successful reads, lock wait, validation stages, malformed record identity, or subprocess details in a stable machine format. There is no Web UI yet, so there are no request, refresh, index, cache, or child-process logs.

Immutable mailbox events and turn settlements are durable domain records. They are not logs. A future logging system must not replace, repair, infer, or mutate those records. Logs may explain what one process observed or failed to do. Durable state remains authoritative for what ZXRO committed.

This is a ZXRO-wide core CLI gap, not a Web UI feature. Humans, hooks, CI, future runtime integrations, and the Web UI need the same opt-in logging contract. Implement the core CLI foundation first. The Web UI later reuses it and adds request/refresh events at its own boundary. Defaults for ordinary CLI users must remain compatible, including empty stderr on successful commands unless logging is explicitly enabled.

## Operator questions and honest answers

| Operator question | Merged evidence | MVP answer |
|---|---|---|
| What is current? | Watchtower records, work `open|closed`, running or settled turns, unread envelopes, bounded summaries | Yes, within one selected home and one refresh snapshot |
| What happened? | Settled turns and their timestamps; currently unread events and generation order | Partly. Full mailbox history is unavailable after ack or handle through the public CLI |
| What decisions were made? | Free-form settlement summaries and deliberate artifacts may mention decisions | Unknown as structured fact. Show source text and immutable references, never a generated decision ledger |
| Why did this happen? | Work ownership, turn binding, settlement source, event-to-turn relationship | Partly. There is no parent turn, `caused_by`, workflow edge, or decision-to-action link |
| Was this a retry or recovery attempt? | Several turns may share work, agent, session, or cwd | Unknown. Repetition is not a durable attempt model |
| What is blocked? | A summary or artifact may contain blocker language | No structured answer. Keyword matches may be shown only as search results |
| What evidence supports an outcome? | Summary, artifact reference, payload digest, event ID, turn ID, generation, settlement source and time | Yes for references and provenance. Artifact body viewing needs a pure read contract |
| Is a running turn stale? | Running state and session binding | Unknown. Running turns have no creation or heartbeat timestamp |
| Were retries or conflicts observed? | Current terminal settlement only | No. Idempotent retries and rejected conflicts leave no durable audit item |
| Which prompt or workflow should improve? | Outcomes, agent/session/cwd, bounded summaries, optional payload artifacts | Only local, evidence-linked signals. Prompt attribution is unavailable because prompt identity and text are not durable fields |

## Information architecture

### Global shell

The shell shows the selected home as a masked label, CLI capability status, snapshot time, refresh state, and integrity warnings. One process binds to one explicit `$ZXRO_HOME`. It does not discover or switch among homes.

Primary navigation:

1. Overview
2. Watchtowers
3. Work
4. Mailbox
5. Artifacts
6. Analysis
7. Integrity

Unavailable sections remain absent until their required CLI contract exists. A disabled control that looks actionable is worse than no control.

### Overview

Show:

- watchtower, work, and turn counts;
- open and closed work counts;
- running and settled turn counts;
- completed, failed, and cancelled settled-turn counts;
- unread count per watchtower;
- refresh age and any degraded capability.

Every ratio names its denominator. For example, `failed settlements / settled turns with a recognized outcome`, not "failure rate" without qualification.

### Watchtower view

Show the watchtower ID, masked project cwd, optional agent and session, owned work, unread events, and later mailbox status. Do not imply that the watchtower process is alive. M0/M1 store identity and routing metadata, not runtime liveness.

### Work list and work detail

The list supports exact state and watchtower filters plus text search over loaded public fields. Work detail shows:

- stable work ID, owner, and current `open|closed` state;
- related turns;
- settled summaries and provenance;
- related events where the CLI exposes them;
- artifact references;
- explicit unknown labels for creation time, close time, current assignee, priority, attempt count, and blocker state.

Until mailbox history exists, call the sequence a "known turn sequence," not a complete timeline. `turn list` is sorted by UUID, not chronology. Settled turns may be ordered by `settled_at` with a note that mailbox generation is the canonical per-watchtower order when available. Running turns have no reliable chronological position.

### Turn detail and recovery references

Show the separate ZXRO and runtime identities:

- turn, work, and watchtower IDs;
- runtime, agent, session, and masked crew cwd;
- optional native session ID behind an explicit reveal;
- running or settled state;
- outcome, summary, source, settled time, payload digest, stable event ID, and artifact references when settled.

The page may link to the native recovery playbook. It must not construct provider resume commands, inspect native stores, claim exact resume support, or contact acpx, Pi, or Claude.

### Mailbox view

The desired view separates:

- immutable event identity and generation;
- unread delivery state derived from ack;
- pending attention derived from handled state;
- work closure as a separate axis.

The first slice may show unread only. Pending requires a pure read command. Complete history, handled timestamps, and ack/high-water status require future core CLI reads. The UI never offers ack or handle controls.

### Artifact view

Before a pure artifact command exists, show only references already present in turn or event JSON. Do not call `artifact path`, inspect `artifacts/`, derive filenames, or decode local JSON.

After the proposed read contracts merge, show metadata first. Body retrieval is deliberate, size-bounded, off by default, and never included in routine refresh or search indexing.

### Analysis view

Analysis runs locally over one coherent snapshot. Initial useful statistics are:

- work counts by current state and watchtower;
- turn counts by state, outcome, agent, and exact session value;
- settled-outcome proportions with `settled turns` as denominator;
- counts of distinct cwd values, with cwd masked by default;
- counts of summaries scanned and exact keyword matches;
- repeated normalized summary fingerprints, presented as repetition rather than retries;
- failed and cancelled settlements linked to their turn and event evidence.

Do not call these measures productivity, quality, success of a prompt, recovery rate, or causal effect. Session names are arbitrary strings, not durable workflow roles.

Prompt and workflow opportunity cards must include:

- the rule that produced the card;
- numerator and denominator;
- the snapshot time;
- links to the turn, event, summary, and deliberately opened artifact evidence;
- a label such as `search signal`, `repetition signal`, or `outcome cluster`;
- a statement that ZXRO has no prompt version or causal attribution for the observation.

Examples include several failures for one exact session string, repeated cancellation summaries, or repeated blocker keyword matches. These are triage leads, not decisions.

### Integrity view

Show capability-specific failures without laundering unsafe state into partial facts:

- exit 2: UI or CLI contract/configuration error;
- exit 3: missing home or object;
- exit 4: unexpected conflict from a read path;
- exit 5: unsafe or malformed durable state;
- timeout, output limit, invalid JSON, or executable mismatch.

If `turn list` or any other required read fails, the UI publishes no new current snapshot. Independently successful results from that attempt appear only as bounded diagnostics marked partial. Resource views continue to show the complete prior snapshot as stale with its original observation time and stale age, or show current data unavailable when no prior successful snapshot exists.

## CLI-to-view capability matrix

`Safe now` means the merged implementation takes no ZXRO mutation path. It does not mean the command is side-channel free on every filesystem.

| Public CLI capability | JSON shape now | UI view | Read status | Parity rule and test |
|---|---|---|---|---|
| `watchtower list` | Array of watchtower records | Overview, watchtower list | Safe now | Adapter output equals CLI records field for field |
| `watchtower show <id>` | One watchtower record | Watchtower detail | Safe now | Detail equals `show`; list-to-detail identity must match |
| `work list [filters]` | Array of work records | Overview, work list | Safe now | Unfiltered ingest is authoritative; UI filters must match CLI filter results |
| `work show <id>` | One work record | Work detail | Safe now | Current state and owner equal CLI output |
| `turn list [filters]` | Array of full running or settled turn records | Work history, turns, analysis | Safe now | No artifact body or inferred order added |
| `turn show <id>` | One turn record | Turn detail, provenance, recovery references | Safe now | Every displayed durable field comes from the CLI record |
| `inbox unread --watchtower <id>` | Array of bounded events | Unread mailbox, known event sequence | Safe now | Event IDs and generations equal CLI order and contents |
| `inbox pending --watchtower <id>` | Array of bounded events | Pending attention | Not safe for a strict viewer. Current implementation may compact state | UI command allowlist rejects it until a physically read-only contract merges |
| `artifact path <ref>` | `{ref,path,bytes}` in JSON; path in human mode | Artifact metadata and deliberate evidence access | Not safe for a strict viewer. It may materialize a `.bin` file | UI command allowlist rejects it until pure stat/read contracts merge |
| `ack` | Ack result from a mutation | Mailbox read position | Mutation, forbidden | UI never invokes it. A new status read is required |
| `inbox handle` | Handled record from a mutation | Handled state | Mutation, forbidden | UI never invokes it. History/status reads are required |
| `work close` | Closed work record from a mutation | Current work state | Mutation, forbidden | UI reads the result later through `work show|list` |
| `turn create|settle` | Created or settled turn record | Turn state and evidence | Mutation, forbidden | Test fixtures may seed state outside the running UI; the app never invokes these verbs |
| `watchtower create`, `work create` | Created record | Registry/work state | Mutation, forbidden | Same fixture-only rule |
| `inspect` | None on `master` | Bounded joined work diagnosis and counts | Unavailable M2 | No MVP dependency or fallback; a future UI may consume its JSON after parity and purity review |
| `turn env` | None on `master` | Read-only `ZXRO_*` metadata formatting | Unavailable M2 | Not needed by current views; never evaluate shell output |
| `turn bind` | None on `master` | Mutating, idempotent late native-session enrichment | Unavailable M2 | View-only UI never invokes it; display later public results only |
| `turn run` | None on `master` | Child process launch with turn metadata | Deferred beyond M2 | Never a view-only UI operation |

### Parity acceptance suite

Create state through public mutation commands in a temporary home, then start the UI in a separate process. Fixture setup is not part of the application.

For each safe command:

1. capture exact `--json` output;
2. refresh the UI adapter;
3. compare the adapter's normalized record to the CLI record field for field;
4. verify list filters and UI filters return the same IDs;
5. verify Unicode, absent optional fields, all terminal outcomes, and several watchtowers;
6. verify unknown additive public fields do not break the adapter, and keep them undisplayed until the UI schema reviews them;
7. verify no UI label claims a field the CLI did not return.

For forbidden commands, replace the subprocess runner with a spy and fail the test if argv contains `create`, `close`, `settle`, `ack`, `handle`, `inbox pending`, or `artifact path`. After startup, refresh, navigation, search, and artifact-reference selection, compare the set and content digest of all files under the temporary home. No file may appear, disappear, or change. In particular, no `.bin` artifact materialization may appear and mailbox bytes must remain unchanged.

## Read contract gaps and opportunities

### Classification key

- `Parity blocker` prevents strict view-only parity with data a merged CLI command can expose.
- `Useful enhancement` answers an operator question that the merged public CLI cannot answer cleanly.
- `Speculative` needs usage evidence or later automation before a contract should be fixed.
- `Core CLI` belongs in provider-neutral ZXRO behavior.
- `Optional extension` may live in the Web UI package or another local analysis tool, but it still consumes public CLI data.

The proposed commands below do not exist on `master`.

### Gap register

| ID | Classification | Owner | Data basis | Delivery horizon | Priority |
|---|---|---|---|---|---|
| G1 | Parity blocker | Core CLI | Available mailbox and handled data | Current prerequisite | P0 |
| G2 | Parity blocker | Core CLI | Available artifact metadata/content | Current prerequisite | P0 |
| G3 | Useful enhancement | Core CLI | Available immutable event, ack, and handled data | First useful history milestone | P1 |
| G4 | Useful enhancement | Core CLI | Available mailbox state | First useful history milestone | P1 |
| G5 | Useful enhancement | Core CLI | Available records, new consistency token | Post-MVP optimization | P2 |
| G6 | Useful enhancement | Core CLI | Existing public schemas plus G19 logging schema | After G19, before Web UI | P0 |
| G7 | Useful enhancement | Optional extension | Available loaded metadata | MVP | P1 |
| G8 | Useful enhancement | Optional extension | Artifact access depends on G2 | Post-MVP | P2 |
| G9 | Useful enhancement | Core CLI | New durable timestamps | Future schema | P2 |
| G10 | Useful enhancement | Core CLI | New work projection fields | Future schema | P2 |
| G11 | Useful enhancement | Core CLI | New causal and attempt fields | Future schema | P2 |
| G12 | Useful enhancement | Core CLI | New decision records or typed artifacts | Future schema | P2 |
| G13 | Useful enhancement | Core CLI | New blocker/evidence semantics | Future schema | P2 |
| G14 | Useful enhancement | Core CLI | New retry/conflict audit events | Future schema | P3 |
| G15 | Useful enhancement | Core CLI | New prompt/template provenance | Future schema | P3 |
| G16 | Useful enhancement | Core CLI | New artifact media/privacy metadata | Future schema | P2 |
| G17 | Speculative | Optional extension | External runtime status | Deferred with runtime integration | P3 |
| G18 | Speculative | Optional extension | Future M7 policy and workflow events | Deferred M7 or later | P3 |
| G19 | Useful enhancement and prerequisite | Core CLI | Process observations, no durable-schema change | Pre-Web-UI core foundation | P0 |
| G20 | Useful enhancement and consumer instrumentation | Optional extension | UI and child-process observations, no durable-schema change | Reuse G19 before feature views | P0 |
| G21 | Useful enhancement | Core CLI | Available durable validation results | First diagnostics milestone | P1 |

### G1. Physically read-only pending attention

- Operator question: "Which actionable events still need attention without changing durable state?"
- Proposed contract: add `zxro inbox pending --watchtower <id> --read-only`. JSON remains an array of bounded event envelopes. The flag guarantees no compaction, marker creation, lock-file creation, or provider write. A later compatibility decision may make pure reads the default and move compaction to mutation paths or an explicit maintenance command.
- Schema and versioning: retain the existing event schema. Advertise the `inbox.pending.read_only` capability and schema revision through G6.
- Security and privacy: same bounded summaries and references as current pending. No bodies. The guarantee must include missing and malformed state.
- Dependencies: durable-store contract clarification and provider conformance hooks that count writes as well as reads.
- Priority: P0 parity blocker in the core CLI.
- Acceptance test: seed marker-committed crash residue, hash the home, invoke the new command repeatedly, and prove identical output and no changed or created path. Results must match ordinary `pending` semantics on clean state.

### G2. Pure artifact metadata and bounded retrieval

- Operator question: "What evidence exists, how large is it, and can I inspect a deliberate slice without materializing a file?"
- Proposed contracts:

  ```text
  zxro artifact stat <ref>
  zxro artifact read <ref> --offset <n> --limit <n> --format base64
  ```

  `stat` returns a versioned envelope containing provider-neutral `ref`, `kind`, and `bytes`, plus optional digest and media metadata when the provider can prove them. `read` returns `ref`, `offset`, `returned_bytes`, `complete`, optional digest, and `data_base64`. It enforces a small maximum chunk. It does not return or create a local path.
- Schema and versioning: new commands use `{schema_version:1,...}` envelopes. Optional fields follow contract conventions. Existing `artifact path` remains unchanged and is never used by the UI.
- Security and privacy: artifact data is high risk. No prefetch, bulk endpoint, routine indexing, browser persistence, logs, or URL parameters containing content. Apply server response limits and `Cache-Control: no-store`.
- Dependencies: provider-neutral `artifact.stat` and range-read capability. Providers that cannot range-read may return an explicit unsupported capability rather than a path.
- Priority: P0 for metadata parity. Body preview may follow at P1 after a privacy review.
- Acceptance test: compare `stat.bytes` with existing `artifact path --json` on a disposable copy, then prove stat/read create no `.bin`, do not alter home bytes, reject traversal, verify digest where supplied, enforce range bounds, and never include content in routine snapshot output.

### G3. Immutable mailbox history with read and handled axes

- Operator question: "What happened before the current unread and pending windows, and which events were observed or handled?"
- Proposed contract:

  ```text
  zxro inbox history --watchtower <id> --after-generation <n> --limit <n>
  ```

  Return `{schema_version,watchtower_id,events,next_after_generation,complete}`. Each item contains the immutable event plus `read: boolean`, `handled: boolean`, and optional `handled_at`. Generation remains canonical order.
- Schema and versioning: version the page envelope and history item. Keep the embedded event compatible with current public event JSON.
- Security and privacy: pagination and output caps are mandatory. History still contains bounded summaries, cwd-free event metadata, and artifact references, not artifact bodies.
- Dependencies: promote the optional durable-store `mail.since` behavior and add handled-state lookup to the provider-neutral read capability.
- Priority: P1 core CLI enhancement. It is required for an honest complete mailbox timeline, retry-independent handled statistics, and post-ack history.
- Acceptance test: publish, ack, and handle events out of order; page through every generation; assert immutable event equality, exact read and handled flags, stable ordering, no writes, and no skipped or duplicate generation under concurrent settlement.

### G4. Mailbox status

- Operator question: "How far has this watchtower read, what is highest, and how much delivery or attention remains?"
- Proposed contract:

  ```text
  zxro inbox status --watchtower <id>
  ```

  Return `{schema_version,watchtower_id,ack_generation,highest_generation,unread_count,pending_count}` with strict integers and an optional integrity status.
- Schema and versioning: versioned envelope. Counts name their exact set. Do not add a generic health score.
- Security and privacy: counts disclose workload shape but no body. Treat them as home-private data.
- Dependencies: pure pending semantics from G1 or a provider count operation with the same validation.
- Priority: P1 core CLI enhancement.
- Acceptance test: verify status through publish, ack past unhandled events, out-of-order handle, and work close. Ack, pending, and close remain independent. Repeated status calls leave the home unchanged.

### G5. Coherent multi-resource snapshot

- Operator question: "Did these joined records describe one point in durable state, or did writers change the home between commands?"
- Proposed contract:

  ```text
  zxro state snapshot --include watchtowers,work,turns,mailbox-status
  ```

  Return one bounded, versioned envelope with a provider-issued `snapshot_id`, `observed_at`, included collections, and capability errors. Artifact bodies and full mailbox history stay excluded.
- Schema and versioning: top-level `schema_version` plus per-capability revisions. A snapshot ID proves equality only within one home and provider; it is not a global event order.
- Security and privacy: one response aggregates sensitive paths and session references. Apply output caps and never log the body.
- Dependencies: shared or equivalent provider read consistency. G1 and G4 must already define pure mailbox projections.
- Priority: P2 core CLI enhancement. MVP can use guarded multi-command refresh first.
- Acceptance test: run 12 concurrent settlements during repeated snapshots. Every successful snapshot must have internally valid ownership and references. It may show state before or after a write, never a torn cross-record mix.

### G6. Machine-readable capabilities, versions, and errors

- Operator question: "Which read contracts does this CLI support, and did a read fail because of missing, conflicting, or unsafe state?"
- Proposed contracts:

  ```text
  zxro --json version
  zxro --json capabilities
  zxro --json-errors <existing read command>
  ```

  Capabilities return command, output, and logging schema revisions without probing mutating commands. With structured logging disabled, JSON errors use stderr and contain `schema_version`, stable `code`, exit class, and bounded message. With G19 JSONL enabled, stderr contains one schema-valid JSON event per line and the final invocation event carries the same error object.
- Schema and versioning: these commands establish explicit revisions for new envelopes. Existing unversioned record outputs remain compatible and additive.
- Security and privacy: version output must not include environment variables, home contents, or executable search paths. Errors must not dump raw records or artifact content.
- Dependencies: the G19 logging event schema must be defined first so G6 can consume and advertise its version, plus a contract-conventions update and stable error identifiers. G19 does not depend on G6.
- Priority: P0 core CLI prerequisite after G19 and before reliable adapter negotiation. MVP may pin one CLI version, but it still needs a deterministic unsupported-capability screen.
- Acceptance test: exercise exit codes 2 through 5, malformed JSON state, missing home, and unsupported future capabilities. Stdout remains one JSON value only on success. Error-only mode emits one bounded JSON value on stderr; G19 mode emits schema-valid JSONL with an equivalent final error object.

### G7. Snapshot search and filters

- Operator question: "Where does this ID, session, outcome, or summary text occur in the state I already loaded?"
- Proposed extension: client-side or server-memory search over the current snapshot. No new core command is needed for MVP. Search fields are explicitly listed and results retain resource IDs and source commands.
- Schema and versioning: optional Web UI `/api/v1/search` response version, or client-only implementation tied to the snapshot API revision.
- Security and privacy: do not send queries anywhere, store recent searches, index artifact bodies, or search unrelated homes.
- Dependencies: safe current reads and one coherent UI snapshot.
- Priority: P1 optional extension.
- Acceptance test: compare exact ID/state filters with CLI filter results; verify search never returns fields excluded by redaction or a previous snapshot.

### G8. Artifact-aware local analysis

- Operator question: "Which deliberately selected evidence contains repeated failure or blocker language?"
- Proposed extension: opt-in analysis over artifact chunks fetched through G2. Keep an in-memory list of inspected refs. Results state the query, bytes scanned, artifacts scanned, matches, and omissions.
- Schema and versioning: version analysis-rule output separately from durable data. Do not persist findings as ZXRO facts.
- Security and privacy: disabled by default. No automatic fetch, whole-home indexing, disk cache, telemetry, or model/provider calls.
- Dependencies: G2, content-size limits, and an operator privacy decision.
- Priority: P2 optional extension.
- Acceptance test: prove only explicitly selected refs are read; denominators and truncation are visible; binary or undecodable chunks produce `unknown`, not fabricated text.

### G9. Lifecycle timestamps and staleness inputs

- Operator question: "How long has work or a running turn been open, and when was it closed, acknowledged, or handled?"
- Proposed future fields: `work.created_at`, `work.closed_at`, `turn.created_at`, optional runtime observation time, and `acknowledged_at`. Keep `handled_at` already represented in handled state.
- Proposed read output: additive fields in `work show|list`, `turn show|list`, mailbox status, and history. No `stale` boolean belongs in durable state without a policy owner.
- Schema and versioning: new durable schema revision and explicit M0/M1 compatibility plan. Older records retain absent fields and yield unknown age.
- Security and privacy: timestamps reveal operator activity patterns. Keep them local and avoid fine-grained telemetry beyond contract needs.
- Dependencies: migration and downgrade review.
- Priority: P2 core CLI and durable-schema enhancement.
- Acceptance test: creation and transition timestamps survive process exit, retain offsets, never define identity/order, and render unknown for legacy records. Stale UI rules name their threshold and denominator.

### G10. Richer current work projection

- Operator question: "What is the latest accepted context for this work without replaying every turn?"
- Proposed future fields: bounded work summary, explicit current or latest relevant turn refs, blocker count only when backed by typed blocker state, and update time.
- Proposed read output: additive `work show` projection with references, not artifact bodies or copied history.
- Schema and versioning: durable work schema revision. References must be validated across provider capabilities.
- Security and privacy: bounded summaries can still contain secrets. Apply the same local-only posture as turn summaries.
- Dependencies: product decision on who updates the projection and conflict semantics.
- Priority: P2 core CLI enhancement with new durable data.
- Acceptance test: many-turn work reads remain bounded; references resolve; closing work does not rewrite history; malformed references fail closed.

### G11. Attempts and causal chains

- Operator question: "Which turn retried or followed which earlier result, and what caused this turn to start?"
- Proposed future fields: optional `parent_turn_id`, `caused_by_event_id`, typed `purpose` or workflow stage, and producer-assigned `attempt` only when the workflow owns a stable attempt definition.
- Proposed read output: additive turn fields plus a future `work graph <id>` bounded edge list.
- Schema and versioning: durable-schema change with cycle checks, same-home ownership checks, and compatibility rules. Do not derive attempt order from UUID, session, cwd, or summary.
- Security and privacy: causal metadata can expose workflow policy and task intent. Keep prompts and arbitrary commands out of edge fields.
- Dependencies: M7 or another workflow owner must define edge creation semantics first.
- Priority: P2 core CLI opportunity, deferred until a real producer exists.
- Acceptance test: reject cross-home, missing, self, and cyclic links; retain links after close; prove graph order does not invent causality for legacy turns.

### G12. Decisions and provenance

- Operator question: "What decision was made, by whom or what, from which evidence, and was it superseded?"
- Proposed future contract: a typed, immutable decision record or typed artifact metadata with decision ID, bounded statement, source turn/event, evidence refs, recorded time, optional supersedes ID, and recorder identity class.
- Proposed read output:

  ```text
  zxro decision list --work <id>
  zxro decision show <decision-id>
  ```

- Schema and versioning: a new contract and durable object family. Free-form summary extraction never becomes an authoritative decision.
- Security and privacy: decisions may contain sensitive rationale. Keep statements bounded, evidence referenced, and body retrieval deliberate.
- Dependencies: architecture decision on ownership and mutability. This is not needed for M0/M1 parity.
- Priority: P2 core CLI opportunity with new durable schema.
- Acceptance test: immutable identity, evidence resolution, supersession without deletion, bounded reads, and explicit unknown for work with no decision records.

### G13. Blockers and evidence claims

- Operator question: "What currently blocks this work, who asserted it, and what evidence supports or clears it?"
- Proposed future contract: typed blocker records or work-scoped claims with status, source turn/event, evidence refs, recorded time, and resolution reference.
- Proposed read output:

  ```text
  zxro blocker list --work <id> --state open
  zxro blocker show <blocker-id>
  ```

- Schema and versioning: new durable schema. Keyword matches stay search signals and never populate blocker state.
- Security and privacy: blocker text may reveal vulnerabilities. Bound summaries and keep evidence behind refs.
- Dependencies: decision on claim ownership and resolution semantics.
- Priority: P2 core CLI opportunity.
- Acceptance test: open and resolved states remain distinct from work close and mailbox handled; every transition retains provenance and cannot erase evidence.

### G14. Retry and conflict audit

- Operator question: "How often did producers retry, conflict, or fail before durable settlement?"
- Proposed future contract: bounded audit events for rejected or idempotent mutation attempts, with operation class, stable target, result class, timestamp, and non-secret producer identity. Never store raw conflicting payloads.
- Proposed read output:

  ```text
  zxro audit list --work <id> --kind settlement_attempt --limit <n>
  ```

- Schema and versioning: a new append-only audit contract with retention and pagination. Current state cannot reconstruct this history.
- Security and privacy: audit data can expose behavior and identifiers. Define retention, avoid payload copies, and keep local by default.
- Dependencies: concrete operator demand and storage-cost review.
- Priority: P3 core CLI opportunity, deferred.
- Acceptance test: identical retry, conflicting retry, validation failure, and process interruption produce the specified bounded audit result without changing settlement idempotency or leaking payload bytes.

### G15. Prompt and template provenance

- Operator question: "Which prompt or workflow version produced these outcomes?"
- Proposed future fields: non-secret `prompt_template_id`, `prompt_template_version`, workflow policy version, role/stage, and optional prompt artifact ref. Full prompt text is not required and should not enter routine output.
- Proposed read output: additive turn provenance fields and exact filters. Deliberate prompt-artifact reading uses G2.
- Schema and versioning: durable turn-schema change. Define producer ownership before capture.
- Security and privacy: prompts may contain source, customer data, or secrets. Default to identity/version only. Prompt bodies require explicit capture and redaction policy.
- Dependencies: M5/M6 producers or M7 workflow must supply trustworthy provenance.
- Priority: P3 core CLI opportunity, deferred.
- Acceptance test: compare outcomes only within exact known versions; legacy or missing provenance remains `unknown`; no UI analysis attributes causation from correlation.

### G16. Artifact media and privacy metadata

- Operator question: "Can this artifact be rendered safely, and does policy permit displaying it?"
- Proposed future fields: media type, text encoding, sensitivity label, capture source, redaction status, and optional immutable content digest where provider-neutral.
- Proposed read output: additive fields from `artifact stat`; body remains separate.
- Schema and versioning: artifact contract revision with optional fields. Providers must not guess a media type from a filename alone.
- Security and privacy: sensitivity and redaction labels inform display but do not prove content is safe. Unknown defaults to no inline render.
- Dependencies: artifact policy and producer support.
- Priority: P2 core CLI enhancement with new durable metadata.
- Acceptance test: unknown/binary artifacts never render inline; declared text still passes output limits and browser escaping; labels survive provider round trips.

### G17. Live runtime status

- Operator question: "Is the external session working, idle, stopped, gone, or unknown right now?"
- Proposed extension: a separate, opt-in runtime adapter view that calls a future public runtime describe command. It must not infer work acceptance or settlement.
- Schema and versioning: runtime status schema separate from durable snapshot schema, with observation time and capability provenance.
- Security and privacy: contacting a runtime may expose presence and may invoke provider tooling. Keep disabled in the durable-state MVP.
- Dependencies: future runtime port implementation and provider availability. No silent acpx or native-store calls.
- Priority: P3 speculative optional extension.
- Acceptance test: unavailable runtime yields `unknown`; status cannot close work, settle turns, handle events, or alter durable state.

### G18. Workflow recommendation and M7 events

- Operator question: "What should happen next, and can the system route it automatically?"
- Proposed extension: none in this initiative. Future M7 may add typed workflow decisions and dispatch outcomes through public durable contracts.
- Schema and versioning: undecided. Any recommendation schema must separate observed evidence, policy decision, and executed action.
- Security and privacy: automated routing can start billable or privileged work. It requires explicit authority and audit.
- Dependencies: M5 or M6 completion producer and M7 watchtower loop.
- Priority: P3 speculative and deferred.
- Acceptance test: defined by M7. The Web UI remains view-only even if M7 exists later.

### G19. ZXRO-wide structured core CLI diagnostics

- Operator question: "What did this CLI invocation read or attempt, where did it fail, and how long did each stage take?"
- Proposed global contract:

  ```text
  zxro \
    [--log-level off|error|warning|info|debug] \
    [--log-format human|jsonl] \
    [--log-file PATH] \
    [--correlation-id OPAQUE_ID] \
    [--log-sensitive] \
    [--home PATH] [--json] <command> ...
  ```

  `off` is the default and emits no structured events. Thresholds are inclusive: `error` admits error events, `warning` admits warning and error, `info` admits info/warning/error, and `debug` admits every defined level. With logging enabled and no `--log-file`, logs use stderr. `human` produces bounded one-line diagnostics for operators. `jsonl` produces one JSON object per line for wrappers. A single `json` format is intentionally absent because one invocation may emit several events. Stdout is never a log destination. `--json` continues to control command results only.

  Carefully scoped environment equivalents are useful for hooks and CI: `ZXRO_LOG_LEVEL`, `ZXRO_LOG_FORMAT`, `ZXRO_LOG_FILE`, and `ZXRO_CORRELATION_ID`. Explicit flags override these variables, which override defaults. Do not honor generic `DEBUG`, `LOG_LEVEL`, or provider variables. Do not provide an environment equivalent for `--log-sensitive`. The first version should not discover a config file because config search would add another path and trust boundary.

  Validate logging flags and environment values before provider access. Correlation IDs are bounded opaque strings with a closed character set. A log file is explicit, must resolve outside the active `$ZXRO_HOME`, and must pass owner, permission, file-type, parent-directory, and symlink checks. File-backed logs use the fixed retention defaults in this plan unless a later contract adds bounded retention flags.

  Required events cover every public CLI command, not only reads. They include invocation start/completion, command dispatch, provider read or mutation start/completion/failure, state validation failure, lock wait where applicable, settlement publication stages, and artifact verification. Each completion includes exit code and elapsed milliseconds. A mutation log may report that the command returned success or failed at a named stage. It cannot replace the durable record as proof of commit.
- Output and exit behavior: with logging off, successful stderr remains empty and failures keep the current bounded human diagnostic. With `--log-format jsonl` to stderr, every stderr line follows the log schema. Every invocation with a level other than `off` constructs exactly one terminal `zxro.cli.invocation.completed` event, even when its success level would otherwise fall below the threshold. The terminal event is the final and highest-sequence event and carries `process_exit_code` plus overall `result_code` or `error_code`. A healthy enabled sink receives it exactly once. Stage events never carry `process_exit_code`; they use `result_code` on success or stable `error_code` on failure. With `--log-file`, normal command stderr keeps its current behavior while structured events go to the file. Invalid logging configuration exits 2 before state access. A runtime sink, append, rotation, formatting, or redaction failure disables that sink, emits at most one bounded fallback warning when possible, and never changes the underlying command exit code, retries a mutation, or redirects logs to stdout or `$ZXRO_HOME`.
- Schema and versioning: every event contains `log_schema_version`, stable `event_name`, `event_version`, `timestamp`, `level`, `invocation_id`, per-invocation `sequence`, optional validated correlation fields, and a typed `attributes` object. Sequence starts at 1 and increments by 1 after threshold filtering, so a healthy stream has no gaps and the terminal event has the largest value. Event names use a stable namespace such as `zxro.cli.invocation.completed` and `zxro.state.validation.failed`. Additive attributes are allowed. Renaming an event or changing attribute meaning requires a new event version.
- Security and privacy: default events omit argv values, cwd, home path, prompt/summary/artifact content, stdin, environment, session/native IDs, and raw records. Resource correlation uses process-local keyed fingerprints by default. `--log-sensitive` may include raw ZXRO IDs and masked path tails, but never credentials, prompts, payloads, artifact bodies, cookies, authorization data, or raw environment values.
- Dependencies: only a core logging contract, a clock abstraction for tests, redaction helpers, and sink primitives including safe concurrent append/rotation. G19 does not depend on G6, a durable-schema change, a UI package, or a provider adapter.
- Priority: P0 core CLI prerequisite and ZXRO-wide opportunity before Web UI implementation. It benefits shell operators, hooks, CI, M5/M6 producers, and later M7 work independently from the UI.
- Acceptance test: every merged command class emits schema-valid ordered events only when enabled; threshold matrices pass; stdout bytes and command-result JSON remain exact; normal logging-off stderr remains compatible; human and JSONL formats carry equivalent event meaning; flags and environment precedence are deterministic; each healthy stream has contiguous sequence and exactly one final `invocation.completed` whose `process_exit_code` matches the process; stage events use only result/error codes; elapsed time is non-negative; malformed/conflicting/unsafe cases have stable names; no fixture secret or path appears; exact rotation, retention, and permissions pass; logging failure cannot alter command behavior or durable state.

### G20. Web UI request, refresh, child-process, and index diagnostics

- Operator question: "Why is this page stale or degraded, which CLI read failed, and was the problem parsing, indexing, timeout, or unsafe state?"
- Proposed extension: a G19 consumer plus Web UI boundary instrumentation and an accessible diagnostics page. It does not implement or redefine core CLI logging. Web event families cover server lifecycle, HTTP request completion, refresh start/completion/failure, child CLI start/completion/timeout/output-limit, JSON decode/schema failure, snapshot instability/retry, index build timing/failure, redaction counts, and stale-snapshot fallback.
- Schema and versioning: reuse the G19 envelope where practical and add Web event names such as `zxro.web.refresh.failed` and `zxro.web.cli_child.completed`. Correlate `request_id -> refresh_id -> cli_invocation_id`, then attach available opaque work, turn, runtime/session, mailbox generation/event, and artifact fingerprints. Route templates, not raw URLs or query strings, identify requests.
- Security and privacy: capture child exit code, signal, elapsed time, stdout/stderr byte counts, truncation, and stable error code. Do not log stdout bodies. Store only a bounded, redacted stderr summary or digest unless sensitive detail is explicitly enabled. Never log search text, summaries, prompts, artifact chunks, tokens, cookies, full paths, environment values, or raw session IDs.
- Dependencies: G19, G6, UI redaction policy, bounded in-memory ring storage, and accessible diagnostics components.
- Priority: P0 Web UI consumer work after the P0 core CLI G19 prerequisite and before Web UI feature views.
- Acceptance test: inject child exit codes 2 through 5, timeout, invalid JSON, oversized output, malformed state, concurrent refresh, and index failure. The diagnostics view must identify the failing stage and correlations without exposing fixture secrets, changing `$ZXRO_HOME`, or hiding the prior snapshot's stale time.

### G21. Read-only integrity diagnostics command

- Operator question: "Can ZXRO validate this home's readable relationships and explain failures without repairing anything?"
- Proposed contract:

  ```text
  zxro diagnostics check --scope registry,work,turns,mailbox,artifacts --limit <n>
  ```

  Return a versioned summary with each scope's `ok|degraded|failed|not_checked` state, checked item count, bounded stable diagnostic codes, opaque resource fingerprints, truncation, and elapsed milliseconds. It must not return record or artifact bodies and must not repair, compact, materialize, ack, or handle.
- Schema and versioning: `{schema_version:1,observed_at,scopes,complete,duration_ms}` with stable diagnostic codes linked to G19 event names where useful. Human stderr remains separate from JSON stdout.
- Security and privacy: explicit scope and item limits prevent accidental whole-home disclosure or denial of service. Default output omits raw paths and IDs. Sensitive detail is opt-in and local.
- Dependencies: provider-neutral validation reads, pure G1/G2 behavior, and no-write conformance hooks. This command is not a localfs inspector.
- Priority: P1 core CLI enhancement after the minimum logging foundation.
- Acceptance test: validate clean, missing, malformed, conflicting, symlinked, cross-owner, and partial-publication fixtures; prove stable codes, bounded output, exact scope state, and unchanged home path/content digest after repeated checks.

## Smallest sequence that preserves CLI-first parity

1. **Document and enforce the command allowlist.** Safe merged reads are watchtower, work, turn, and unread list/show commands. Ship no UI action that can reach another verb.
2. **Add the G19 minimal CLI logging foundation.** Stable opt-in diagnostics must exist before capability advertisement or UI subprocess wrapping. Preserve current stdout, stderr, exit, and durable behavior when logging is off.
3. **Add G6 capability negotiation.** After G19 freezes its schema, G6 consumes and advertises that version. The UI must know which read and logging contracts exist without probing state or provider files.
4. **Add G1 and G2 in the core CLI.** Pure pending and artifact metadata remove the two strict parity blockers. Do not implement them inside the Web UI.
5. **Build G20 before feature views.** Prove request, refresh, child-process, parsing, redaction, and index diagnostics against synthetic failures.
6. **Build the smallest valuable Web UI slice.** Show current watchtowers, work, turns, unread and pending events, turn provenance, artifact metadata, local search, honest aggregates, integrity state, and manual refresh for one home.
7. **Add G3, G4, and G21.** Mailbox history/status and read-only integrity checks enable a complete known-event timeline and useful operator diagnosis.
8. **Add deliberate artifact chunks and analysis.** Enable G2 body reading and optional G8 only after privacy review.
9. **Add G5 if multi-command refresh proves unstable or expensive.** Do not lead with a bulk snapshot command before individual read contracts settle.
10. **Collect operator evidence before new durable objects.** G9 through G16 require explicit schema decisions and migrations. G17 and G18 stay deferred.

This sequence keeps the CLI authoritative, avoids a localfs dependency, and delivers useful browsing before speculative workflow modeling.

## Smallest valuable vertical slice

The smallest valuable slice is a current-state explorer after G19, G6, G1, G2 metadata, and the G20 consumer instrumentation are ready:

- one explicit home per process;
- overview counts with denominators;
- watchtower and work lists;
- work detail with related turns;
- turn detail with settlement and recovery provenance;
- unread and physically read-only pending views;
- artifact reference and metadata display, without body prefetch;
- exact filters and in-snapshot text search;
- manual refresh and visible snapshot age;
- integrity failures, unavailable-field labels, and an accessible diagnostics panel;
- correlated, redacted refresh and child-process events with bounded in-memory retention;
- no actions, no external provider calls, no localfs reads.

Before those core read gaps merge, a developer prototype may exercise safe reads, but it does not meet parity acceptance and must not be presented as the MVP.

## Ingestion, internal API, indexing, and refresh

### CLI invocation

Use argv arrays, never a shell. Resolve one trusted ZXRO executable at startup and invoke commands equivalent to:

```text
zxro --home <absolute-selected-home> --json watchtower list
zxro --home <absolute-selected-home> --json work list
zxro --home <absolute-selected-home> --json turn list
zxro --home <absolute-selected-home> --json inbox unread --watchtower <loaded-id>
```

After G19 merges, the UI adds fixed logging flags to those same approved reads:

```text
zxro --home <absolute-selected-home> --json \
  --log-level info --log-format jsonl \
  --correlation-id <server-generated-refresh-child-id> \
  watchtower list
```

The server captures command-result JSON from stdout and core diagnostic JSONL from stderr. It does not pass `--log-file`; the UI owns any opt-in retention after redaction. It removes inherited `ZXRO_LOG_*` variables and builds logging values from trusted startup configuration, never an HTTP request. Logging flags cannot alter the command verb or add a mutation. The same argv allowlist and home-digest tests apply with logging on and off.

Add only negotiated pure commands. IDs passed to detail reads must come from a successfully loaded CLI record and still pass public ID validation. Set stdin to null, use a minimal inherited environment, cap output bytes and runtime, and preserve exit code plus bounded stderr for diagnostics.

The server must not import private provider classes. It may own presentation models that preserve source fields and attach UI-only observation metadata.

### Internal read API

The browser talks only to the local Web UI server. Recommended endpoints:

```text
GET /api/v1/capabilities
GET /api/v1/snapshot
GET /api/v1/watchtowers/<id>
GET /api/v1/work/<id>
GET /api/v1/turns/<id>
GET /api/v1/search?q=...
GET /api/v1/artifacts/<encoded-ref>/stat
GET /api/v1/artifacts/<encoded-ref>/chunks?offset=...&limit=...
```

Every successful response uses an envelope like:

```json
{
  "api_version": 1,
  "snapshot_id": "ui-local-digest",
  "observed_at": "2026-08-25T09:35:45+08:00",
  "freshness": "fresh",
  "stale_age_ms": null,
  "consistency": "observational",
  "refresh_failure": null,
  "source": {
    "interface": "zxro-cli",
    "commands": ["watchtower.list", "work.list", "turn.list"]
  },
  "data": {},
  "warnings": []
}
```

Before G5, `snapshot_id` is a SHA-256 digest of the API version, negotiated capability/schema versions, ordered command labels, and canonical successful result digests. It is not a provider transaction token. `consistency: observational` means two bounded observations agreed; it does not mean a writer could not commit immediately after observation.

A failed refresh never publishes a new snapshot. If an earlier successful snapshot exists, `/api/v1/snapshot` returns that exact `snapshot_id`, `observed_at`, and data with `freshness: stale`, `stale_age_ms` measured from the retained snapshot's `observed_at`, and one bounded `refresh_failure`. If no successful snapshot exists, data is unavailable rather than partial. `unstable` and `degraded` are refresh failure kinds shown in diagnostics, not freshness labels attached to partial current data. Errors use a versioned envelope and never include raw artifact bytes.

The server exposes GET and HEAD only. It returns 405 for POST, PUT, PATCH, DELETE, and WebSocket upgrade requests. There is no generic command endpoint.

### Refresh consistency

Pre-G5 refresh is observational, not transactional. One refresh freezes its capability set after a capability preflight, includes the capability result in both passes, and freezes the per-watchtower command roster immediately after pass A's `watchtower list`. The base plan requires `capabilities`, `watchtower list`, `work list`, `turn list`, and `inbox unread` plus G1 pure pending for every watchtower ID in that frozen roster. A negotiated mailbox-status projection becomes required when the snapshot schema includes it. Every required command output is an anchor; there is no smaller weak-anchor subset. Artifact chunks, deliberate artifact stat, search, and other lazy detail reads are not part of the base snapshot and cannot alter it.

Each refresh uses at most three attempts, the initial attempt plus two retries. One attempt follows this exact protocol:

1. Run every required command in a fixed order as pass A. Require exit 0, one bounded JSON result, the negotiated schema, and valid ownership/reference relationships.
2. Canonicalize each result as UTF-8 JSON with sorted object keys, compact separators, and preserved array order. Hash the command label, non-secret argument identity, and canonical result with SHA-256. Hash the ordered vector of those digests.
3. Run the identical command plan as pass B. If pass A's watchtower IDs no longer match pass B, the vector differs and the attempt is unstable; do not add or remove commands mid-attempt.
4. Apply the same parse, schema, relationship, and digest checks to pass B.
5. Succeed only when every required read in both passes succeeds and the complete ordered digest vectors match exactly.
6. Build all current-view indexes and aggregates from pass B only. Index or aggregate failure fails the attempt.
7. Set `observed_at` after the final pass-B check and derive `snapshot_id` from the successful vector. Publish the new snapshot atomically to the UI only after every required read, consistency check, index, and aggregate succeeds.

A read, parse, schema, relationship, index, or aggregate failure ends the current attempt as degraded. A digest mismatch ends it as unstable. Retry the whole protocol, never one command, up to the limit. After the limit, retain the prior successful snapshot as stale. Bounded failure details contain only failure kind, attempt, stage, command label, stable error code, occurrence time, and redaction/truncation flags. Raw stderr, partial records, and artifact content stay out.

Partial pass results exist only as redacted diagnostics marked `partial: true`. They never become `/api/v1/snapshot` data and never feed resource views, search indexes, timelines, counts, ratios, or analysis cards. Never merge passes or attempts. Default to manual refresh plus a conservative, opt-in polling interval such as 30 seconds. Do not watch provider directories.

### Index and cache

Build exact indexes in memory by watchtower, work, turn, event, state, outcome, agent, and session only after a complete refresh passes the protocol above. Search only fields declared in the successful snapshot's UI schema. Do not index artifact bodies or partial refresh results.

MVP has no disk cache, service worker, browser local storage, or cross-restart history. The prior in-memory snapshot may remain visible after a failed refresh, clearly marked stale. If later evidence justifies a disk cache, place it outside `$ZXRO_HOME`, use owner-only permissions, key it by a non-reversible home identifier, and never store artifact bodies or secrets without a separate decision.

## Logging and observability plan

### Authority and failure posture

Durable records answer what ZXRO committed. Structured logs answer what one process observed, attempted, timed, or rejected. A missing log never invalidates a durable record. A log that claims success cannot create settlement, publication, acknowledgement, handled state, work closure, or artifact evidence.

Logging is best effort and fail-open only with respect to diagnostics. If formatting, rotation, or a log sink fails, the CLI or UI reports a bounded logging warning through the remaining sink and continues the underlying command with unchanged semantics. It must not retry a mutation, repair state, or change an exit code merely to satisfy logging.

### Core first, consumers second

G19 is the logging implementation. It belongs to the core CLI and covers every command class. It is useful before any Web UI exists. Hooks, CI, human troubleshooting, and future integrations consume the same flags and event schema.

G20 does not define a competing logger. It reuses the G19 envelope, invokes safe CLI commands with G19 enabled, and adds events only for HTTP, refresh, parsing, indexing, and browser-facing diagnostics that the core CLI cannot observe. Provider adapters may add namespaced attributes through the core logger, but no optional adapter owns the contract.

### Common event envelope

G19 and G20 share this language-neutral envelope:

```json
{
  "log_schema_version": 1,
  "event_name": "zxro.web.cli_child.completed",
  "event_version": 1,
  "timestamp": "2026-08-25T01:35:45.123Z",
  "level": "info",
  "process": "web",
  "invocation_id": "inv-opaque",
  "sequence": 7,
  "correlation": {
    "request_id": "req-opaque",
    "refresh_id": "ref-opaque",
    "home": "home-fingerprint",
    "turn": "resource-fingerprint"
  },
  "duration_ms": 12.4,
  "attributes": {
    "command": "turn.list",
    "result_code": "success",
    "child_process_exit_code": 0,
    "stdout_bytes": 824,
    "stderr_bytes": 0
  }
}
```

Rules:

- Timestamp is RFC 3339 UTC with millisecond precision. Duration uses a monotonic clock and never derives from wall-clock subtraction.
- Levels are `debug`, `info`, `warning`, and `error`, filtered by G19's inclusive threshold rule. The required terminal completion bypasses filtering when logging is enabled. `info` records normal lifecycle, `warning` records degraded but usable behavior, and `error` records a failed requested operation.
- `sequence` is contiguous within one healthy invocation stream and orders events without relying on timestamps.
- `event_name` and `event_version` define semantics. Human prose is optional and never a parser contract.
- Unknown additive attributes are ignored. Required attributes cannot change meaning within an event version.
- IDs generated for diagnostics are opaque and process-scoped unless a caller supplies a validated correlation ID.
- Attribute values are bounded scalars or shallow bounded lists. No raw durable record belongs in an event.

### Stable event families

Minimum core CLI events:

```text
zxro.cli.invocation.started
zxro.cli.invocation.completed
zxro.cli.command.dispatched
zxro.provider.read.started
zxro.provider.read.completed
zxro.provider.read.failed
zxro.provider.mutation.started
zxro.provider.mutation.completed
zxro.provider.mutation.failed
zxro.settlement.publication.stage_completed
zxro.state.validation.failed
zxro.lock.wait.completed
zxro.artifact.verification.completed
zxro.logging.sink.failed
```

Minimum Web UI events:

```text
zxro.web.server.started
zxro.web.server.stopped
zxro.web.request.completed
zxro.web.refresh.started
zxro.web.refresh.retrying
zxro.web.refresh.completed
zxro.web.refresh.failed
zxro.web.cli_child.started
zxro.web.cli_child.completed
zxro.web.cli_child.timed_out
zxro.web.cli_child.output_limited
zxro.web.cli_json.invalid
zxro.web.cli_schema.invalid
zxro.web.snapshot.stale_retained
zxro.web.index.completed
zxro.web.index.failed
zxro.web.redaction.applied
zxro.web.logging.sink.failed
```

Do not emit one event per record during normal refresh. Aggregate counts and timing by command or stage. Debug mode may add bounded per-resource diagnostics, still without content. Core stage events use `result_code` or `error_code`; only `zxro.cli.invocation.completed` uses `process_exit_code`.

### Correlation model

Correlation preserves identity separation:

```text
UI request ID
  refresh ID
    CLI invocation ID
      home fingerprint
      optional work fingerprint
      optional turn fingerprint
      optional runtime/session fingerprint
      optional mailbox event fingerprint + generation
      optional artifact fingerprint
```

A session correlation key includes runtime, agent, session, and cwd identity. It must not collapse to a bare session name. Default logs use keyed process-local fingerprints so repeated values correlate within one run without revealing the raw value. Sensitive-detail mode may expose raw ZXRO work, turn, watchtower, event, and artifact refs in owner-only local logs. It still masks home/cwd paths and never includes prompt, summary, payload, artifact, credential, cookie, or environment content.

The Web UI passes an opaque `correlation-id` to G19 and records the child invocation ID returned in diagnostic events. If a CLI version lacks G19, the UI generates its own child ID and labels core-stage correlation unavailable.

### Subprocess and refresh diagnostics

For every approved CLI child, record:

- command template name, never raw argv;
- start and completion times plus elapsed milliseconds;
- exit code or signal;
- timeout and output-limit status;
- stdout and stderr byte counts;
- parsed stable error code when available;
- whether stderr was truncated or redacted;
- JSON parse and schema result;
- refresh and request correlation.

Do not log stdout bodies. Capture stderr in memory up to a small fixed cap. Run redaction before an event reaches any sink. Default events retain a stable error code, a keyed digest, byte count, and a short redacted summary. Full stderr is available only in explicit sensitive-detail mode and still passes hard secret/content rules.

Refresh diagnostics time capability negotiation, each CLI read, anchor verification, retries, snapshot publication, index construction, redaction, and stale fallback. Performance events report counts and elapsed time, not claims about provider quality. Slow thresholds are configuration values shown in diagnostics.

### Durable-state failure diagnostics

Malformed, conflicting, missing, and unsafe state must retain their current exit class. G19 adds stable failure events with:

- operation stage;
- public exit class and diagnostic code;
- affected capability;
- opaque resource fingerprint when safely known;
- whether any output was discarded;
- whether the prior UI snapshot remains visible;
- elapsed time.

Never include malformed record bytes, external symlink targets, full paths, artifact digests that were not already public, or guessed repair advice. The diagnostics page links to safe operator documentation and G21 results. It offers no repair button.

### Redaction and sensitive detail

Apply redaction before formatting and before retention:

1. Drop environment, stdin, prompt, summary, artifact content, cookies, authorization headers, query strings, and raw stdout unconditionally.
2. Replace home and cwd with a home fingerprint and optional basename class.
3. Fingerprint work, watchtower, turn, session, event, and artifact identity by default.
4. Detect common token, key, credential, and bearer patterns in bounded stderr summaries and replace them with typed placeholders.
5. Enforce per-field and per-event byte limits after replacement.

Sensitive-detail mode is off by default, expires when the process exits, and requires an explicit startup flag. It may reveal raw ZXRO IDs and longer redacted stderr. It may not disable the unconditional drop list. The diagnostics view must show a persistent warning while this mode is active.

Pattern redaction is incomplete. Documentation and UI copy must say so. Tests use synthetic secrets and paths, never real credentials.

### Sinks, isolation, retention, and permissions

Default sinks:

- Core CLI with logging disabled: current stderr behavior only.
- Core CLI with structured logging enabled: JSONL or human logs on stderr unless `--log-file PATH` selects an explicit owner-only file.
- Web UI: redacted warning/error stderr plus an in-memory ring capped at 1,000 events and 2 MiB of serialized event bytes. Before inserting an event, evict the oldest until both limits hold. Track and display the evicted count. The Web UI has no disk retention by default.

For `--log-file PATH`, `PATH` is the active file and `PATH.1` through `PATH.4` are the only backups. The active file plus four backups is a hard maximum of five files. Each file is capped at 5 MiB; rotate before an append would cross the cap, delete `PATH.4`, and shift the other backups atomically under the logging sink's concurrency control. At sink startup and rotation, delete files older than seven days. Size and age rules both apply, so whichever removes an event first defines retention. One event must fit the per-event bound and may never create a sixth file.

Opt-in file retention belongs outside `$ZXRO_HOME`, under an owner-specific state directory partitioned by non-reversible home fingerprint. Set parent directories to `0700`, files to `0600`, reject symlinks and group/world-writable paths, and never share a file between homes.

The UI must not discover another home's logs. Deleting or rotating logs cannot touch durable state. A missing or unwritable log directory cannot trigger creation under `$ZXRO_HOME` as fallback. No system log, cloud log, analytics service, or external collector is enabled in the MVP.

### Operator diagnostics and accessibility

The Integrity section includes a Diagnostics panel with:

- current capability and logging schema versions;
- refresh status, last success, last failure, and stale age;
- stage timings and child exit classes;
- redaction and truncation indicators;
- filters by level, event family, refresh, and opaque resource correlation;
- plain-language explanations linked to stable diagnostic codes.

Use semantic tables or lists, not a color-only console. New error events use an ARIA live region without stealing focus. Keyboard users can filter, expand, and copy one already-redacted event. Timestamps include timezone text. Long JSON is wrapped and has a text alternative. The default view groups repeated events so screen-reader users do not traverse hundreds of identical rows.

### Logging tests

Required tests include:

- default-off compatibility and deterministic flag-over-environment precedence for every approved `ZXRO_LOG_*` variable;
- invalid level, format, file, and correlation configuration exiting 2 before home creation or provider access;
- human and JSONL semantic parity, with no log bytes on stdout and no command-result bytes in log events;
- schema validation and golden events for every stable event name;
- event-version compatibility and unknown additive attributes;
- exact `off|error|warning|info|debug` threshold matrices, with terminal completion retained for every enabled level;
- contiguous per-invocation sequence and exactly one final `invocation.completed` carrying the real `process_exit_code`;
- stage-event `result_code|error_code` rules and rejection of stage `process_exit_code`;
- UTC timestamps, monotonic non-negative durations, and injected-clock determinism;
- request, refresh, CLI invocation, resource, mailbox, session, and artifact correlation;
- subprocess success, exit 2 through 5, signal, timeout, invalid JSON, invalid schema, and output cap;
- malformed, conflicting, unsafe, symlinked, and cross-home state;
- refresh retry, stale fallback, index failure, redaction failure, and log-sink failure;
- synthetic token, prompt, summary, path, session, environment, cookie, and artifact content leakage checks across stderr, files, API, HTML, and browser state;
- sensitive-detail enable/expiry and its unconditional drop list;
- active `PATH`, only `PATH.1` through `PATH.4`, 5-MiB per-file cap, seven-day pruning, maximum five files, safe concurrent append/rotation, owner-only modes, symlink rejection, and separate home partitions;
- Web ring enforcement at 1,000 events and 2 MiB, oldest eviction, visible evicted count, and no default disk file;
- sink-open, append, redaction, formatting, and rotation failures preserving the underlying command exit and never retrying a mutation;
- exact stdout and exit-code parity with logging on and off;
- unchanged `$ZXRO_HOME` path set and content digest after diagnostic emission and G21 checks;
- keyboard, screen-reader labeling, contrast, grouping, and live-region behavior for the diagnostics panel.

## Security, privacy, and trust boundaries

### Home isolation

One server process reads one explicitly selected `$ZXRO_HOME`. It never scans `~/.zxro`, parent directories, sibling homes, provider stores, or native session stores. Starting another home requires another process and capability URL.

Pass the home through the public `--home` option. Let ZXRO enforce ownership, permission, symlink, and managed-path rules. The UI must not weaken a CLI exit 5, follow a symlink to be helpful, or fall back to direct reads.

### Structural prevention of mutation

- Hard-code complete safe argv templates.
- Keep mutation verbs out of code, routing, templates, and help text.
- Reject arbitrary command fragments and shell metacharacters as data.
- Never call `inbox pending` or `artifact path` on the merged baseline.
- Keep caches outside the selected home.
- Open no state file directly.
- Add command-spy and home-digest tests.
- Do not include ack, handle, close, settle, create, bind, run, resume, repair, compact, or dispatch controls.

OS-level read denial is desirable as defense in depth when deployment permits it, but it cannot replace command-level purity because the current CLI validates a user-owned home and some apparently read-like commands take mutation paths.

### Browser and local server

- Bind loopback only. Do not use `0.0.0.0`.
- Generate a high-entropy capability URL, exchange it for an HttpOnly, SameSite=Strict cookie, and remove the token from browser history.
- Validate Host and Origin, disable CORS, and reject DNS-rebinding hosts.
- Serve all HTML, CSS, fonts, and JavaScript locally.
- Use a restrictive CSP with no inline script, `default-src 'self'`, and `connect-src 'self'`.
- Set `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, and frame denial.
- Emit no telemetry, analytics, update checks, CDN requests, or model calls.

### Sensitive fields and redaction

Cwd values, session names, native session IDs, summaries, payload digests, and artifacts may be sensitive. Mask cwd and native IDs by default and reveal them only in the current local page. Never place them in URLs, page titles, server logs, crash dumps, or browser storage.

Metadata summaries remain visible because they are the current routing contract, but the UI must warn that bounded does not mean secret-free. Optional regex redaction must happen server-side before browser delivery, use visible placeholders, report the number of replacements, and admit that pattern redaction is incomplete. Artifact bodies stay hidden until deliberate selection.

## Technology options and recommendation

| Option | Fit | Problems | Decision |
|---|---|---|---|
| Python 3.11 stdlib HTTP server plus server-rendered HTML or small local JavaScript | Matches the dependency-free core, can invoke the CLI directly, easy to run from a checkout | Requires careful HTTP hardening and manual UI discipline | Recommend for MVP |
| Static report generator | Very small attack area after generation | Writes another artifact, becomes stale, and weakens refresh and provenance handling | Keep as a possible later export, not MVP |
| FastAPI plus React and SQLite | Strong ecosystem and browser tooling | Adds runtime/package/build dependencies and a second persistent store before need is proven | Do not choose now |
| Direct localfs reader in any language | Can expose hidden history quickly | Breaks provider neutrality, duplicates validation, bypasses public contracts, and risks unsafe reads | Prohibited |

Add the Web UI as an optional local command or package entry only after its read prerequisites merge. Keep the base CLI usable with Python stdlib alone. A pinned browser-test dependency may be proposed as development-only if stdlib tests cannot provide credible accessibility and browser coverage. That decision needs its own concrete justification under decision 0001.

## Testing strategy

### Required automated tests

- CLI-to-view parity tests from the matrix.
- Command allowlist tests that fail on every mutating or unsafe read-like command.
- Before/after home content and path-set tests.
- Missing home, malformed JSON, wrong ownership, unsafe permission, symlink, record mismatch, and output-limit cases.
- Multi-watchtower and two-home isolation tests.
- Concurrent settlement during refresh, with no torn snapshot presented as fresh.
- Exact pass-A/pass-B canonical digest vectors, watchtower-set changes, full-attempt retry, and the initial-plus-two-retry limit.
- Required read, parse, schema, relationship, index, and aggregate failures retaining the exact prior snapshot with correct stale age and bounded failure details.
- No-prior failure returning unavailable data, plus poison tests proving partial results never enter views, indexes, timelines, counts, ratios, or analysis.
- XSS fixtures in every string field, including summaries, session names, cwd, and stderr.
- Artifact size, binary content, invalid encoding, digest mismatch, and deliberate-fetch tests after G2.
- Redaction tests that verify placeholders, counts, and no raw value in HTML, API responses, logs, or cache.
- API method tests proving mutation methods and generic command routes do not exist.
- Statistics tests that assert numerator, denominator, omitted/unknown count, and source snapshot.

The full existing suite remains mandatory:

```sh
python3 -m unittest discover -s tests -v
```

### Accessibility

Target WCAG 2.2 AA:

- semantic landmarks, headings, tables, lists, and buttons;
- complete keyboard navigation with visible focus;
- no color-only state or outcome encoding;
- accessible names for masked-value reveals;
- live refresh announcements that do not steal focus;
- preserved reading order at narrow widths;
- sufficient contrast and reduced-motion support;
- timestamps rendered with machine-readable `datetime` and an explicit timezone.

Run a manual screen-reader and keyboard pass before MVP acceptance. Add pinned automated browser and accessibility checks only if approved as development dependencies.

## Deployment and operation

The MVP is a foreground local process started with one explicit home. It opens a tokenized loopback URL, serves until interrupted, and writes no ZXRO state. There is no daemon, launch agent, container, hosted service, TLS endpoint, remote bind, user account system, or multi-tenant mode.

Operational output follows G20 and the logging plan. The default stderr sink reports redacted startup, warnings, failures, and shutdown. Detailed structured events stay in the 1,000-event/2-MiB oldest-evicting in-memory ring. The Web UI writes no diagnostic file by default. A health endpoint may report server and CLI capability status but no home counts or identifiers.

Upgrade and rollback replace only Web UI code. Durable migrations do not belong to the MVP. If a future core read contract changes durable schemas, its own compatibility plan precedes UI adoption.

## Milestones

### W0. Documentation and contract review

- Accept this CLI-first boundary and gap register.
- Confirm that G19 is the first core prerequisite, G6 consumes its schema, and G1, G2, and G21 also belong in the core CLI.
- Confirm that G20 is required before Web UI feature work.
- Decide whether a developer-only browser test dependency is acceptable.

Exit: reviewers agree that no direct localfs fallback is permitted, logs never replace durable state, and M2/M7 remain separate.

### W1. Minimal logging foundation

- Specify and implement G19 in separate future core CLI work before any Web UI logging code.
- Freeze global flags, scoped environment equivalents, precedence, destinations, human/JSONL formats, inclusive thresholds, one terminal completion, per-invocation sequence, stage versus process result codes, exact five-file retention, sink-failure behavior, the common event envelope, initial event names, redaction rules, correlation inputs, and stdout/stderr compatibility.
- Exercise every merged read and mutation command class while proving no-secret, no-retry, and no-durable-behavior-change guarantees.

Exit: exact-head CI proves the core CLI flag contract independently from G6 and the Web UI, including success, exit 2 through 5, thresholds, terminal event, sequence, redaction, sink failure, rotation, and correlation. This plan does not perform that implementation.

### W2. Read-purity and parity prerequisites

- After G19 freezes its logging schema, specify and implement G6 so it advertises that schema, then implement G1 and G2 in separate future work.
- Extend provider conformance tests with no-write assertions.
- Keep existing CLI output compatible.

Exit: exact-head CI proves capability negotiation, pure pending, and artifact metadata reads against the built-in provider.

### W3. Smallest valuable slice

- After W2, reuse G19 through G20 and add the exact 1,000-event/2-MiB oldest-evicting in-memory ring plus accessible Web diagnostics components.
- Implement the one-home local server and internal read API.
- Add overview, watchtower, work, turn, unread, pending, artifact metadata, search, integrity, diagnostics, and honest aggregate views.
- Add parity, logging, security, isolation, and accessibility evidence.

Exit: all vertical-slice acceptance criteria below pass without any home mutation.

### W4. History and deliberate evidence

- Add G3, G4, and G21 in the core CLI.
- Add complete mailbox timeline and handled/read statistics.
- Enable bounded artifact chunks and opt-in local analysis after privacy review.

Exit: an operator can trace every published event retained by the provider, diagnose read failures, and follow every UI claim to public CLI evidence.

### W5. Evidence-driven schema evolution

- Collect unanswered operator questions from real use.
- Propose only the needed subset of G9 through G16 as contracts and migrations.
- Keep live runtime status and M7 automation separate.

Exit: each new durable field has an owner, producer, compatibility plan, privacy rule, and conformance test.

## Acceptance criteria

The MVP is acceptable when:

- [ ] It uses the public ZXRO CLI as its only durable-state interface.
- [ ] It provides field-level parity for every approved merged read command.
- [ ] G19 passes as a core CLI contract across every command class before G20 or Web UI feature work.
- [ ] G20 reuses G19 rather than defining another CLI logger or event contract.
- [ ] G1, G2 metadata, and G6 are merged before the product claims strict parity.
- [ ] Structured logs have stable names and versions, complete correlation, bounded timings, and tested redaction without changing stdout, exit codes, retries, or durable records.
- [ ] The UI invokes G19 only through fixed flags on approved read argv, strips inherited logging configuration, and keeps result stdout separate from diagnostic stderr.
- [ ] The application cannot construct or invoke a mutation command.
- [ ] `/api/v1/snapshot` publishes new data only after all required two-pass reads, digest checks, relationships, indexes, and aggregates succeed.
- [ ] Failed refresh retains the exact prior snapshot as stale with correct stale age and bounded failure details; without a prior snapshot, current data is unavailable.
- [ ] Partial refresh results are diagnostics-only and never enter views, indexes, timelines, counts, ratios, or analysis.
- [ ] Pre-G5 copy and diagnostics say observational, not transactional, and tests exercise digest mismatch plus the full three-attempt limit.
- [ ] Repeated startup, refresh, navigation, search, and evidence metadata reads leave every home path and record byte unchanged.
- [ ] One process can observe only its explicit home.
- [ ] Malformed, unsafe, conflicting, missing, stale, unstable, and unknown states have distinct visible treatment.
- [ ] The UI never presents M2 commands, optional adapters, runtime status, or M7 automation as available.
- [ ] Artifact bodies are absent from routine reads, caches, search, logs, and initial HTML.
- [ ] Every aggregate shows its denominator and unknown or omitted records.
- [ ] Every analysis card links to exact public evidence and states that it is not causal proof.
- [ ] Decisions, blockers, retries, attempts, and prompts remain unavailable unless a future durable contract supplies them.
- [ ] Keyboard, contrast, screen-reader, narrow-layout, and reduced-motion checks pass.
- [ ] The existing full test suite and new docs gates pass.
- [ ] Local operation requires no provider, daemon, network service, or third-party runtime dependency.

## Risks and controls

| Risk | Consequence | Control |
|---|---|---|
| A read-like CLI command mutates state | A view changes ack, attention, or artifact files | Purity classification, argv allowlist, G1/G2, home-digest tests |
| UI becomes coupled to localfs | Provider swaps and schema changes break it | CLI-only adapter and no private imports or paths |
| Multi-command refresh tears | False joins and misleading counts | Exact two-pass digest vectors, whole-attempt retry, no partial publication, G5 later if needed |
| Summary text is treated as structured truth | False decisions, blockers, roles, or causality | Explicit unknowns and evidence-linked search signals |
| Artifact previews leak secrets | Sensitive content reaches DOM, cache, or logs | Deliberate bounded reads, no-store, no indexing, masking and redaction |
| Loopback server leaks through browser attacks | Another site reads local state | Capability token, SameSite cookie, Host/Origin checks, no CORS, CSP |
| Statistics imply quality or productivity | Operators make unsupported judgments | Honest names, denominators, omissions, and no causal labels |
| Future M2 or adapter branches drift into scope | Plan depends on unmerged behavior | Baseline capability negotiation and explicit unavailable list |
| New durable schemas arrive too early | Migration cost without operator evidence | Defer G9 through G16 and require owner plus acceptance evidence |
| Logs are mistaken for durable truth | Operators trust a partial process observation over committed state | Authority rule, evidence links, and no state reconstruction from logs |
| Diagnostic detail leaks secrets or crosses homes | Paths, prompts, sessions, or content enter retained files | Pre-sink redaction, unconditional drop list, per-home partition, owner-only limits |

## Open operator decisions and recommended defaults

| Decision | Recommended default | Needed by |
|---|---|---|
| CLI logging default | Disabled for ordinary invocations; opt-in human or JSONL stderr, with explicit file destination available | W1 |
| CLI logging configuration | Global flags override only documented `ZXRO_LOG_*` variables; no discovered config file in the first version | W1 |
| CLI file retention | Active `PATH` plus `PATH.1` through `PATH.4`, each at most 5 MiB and at most seven days, outside `$ZXRO_HOME`; sink failure never changes command exit | W1 |
| UI use of core logging | Fixed `info` plus `jsonl` flags and server-generated correlation on approved reads; strip inherited `ZXRO_LOG_*` | W3 |
| UI log retention | No disk by default; 1,000-event/2-MiB in-memory ring with oldest eviction and visible evicted count | W3 |
| Sensitive diagnostics | Off by default, process-lifetime opt-in, unconditional content/credential exclusions remain | W1 |
| Web UI packaging | Optional local Python stdlib command/package, not a daemon | W3 |
| Browser state | No local storage, service worker, or disk cache | W3 |
| Refresh | Manual plus opt-in 30-second polling; three-attempt two-pass observational protocol and stale fallback | W3 |
| Artifact body access | Disabled until deliberate G2 range reads and privacy review | W4 |
| Path and native ID display | Mask by default, click to reveal in current page only | W3 |
| Redaction | Server-side before every sink, with visible replacement counts and no claim of completeness | W1 |
| Browser test tooling | Prefer a pinned development-only tool if manual evidence proves inadequate; no runtime dependency | W0 |
| Full mailbox history | Core CLI G3, not localfs inspection | W4 |
| New decision/blocker/prompt schemas | Defer until operators produce concrete unanswered cases | W5 |
| Remote access | Unsupported | All MVP milestones |

## Explicit non-goals

- Editing, acking, handling, closing, settling, creating, binding, repairing, resuming, dispatching, or waking from the browser.
- Direct localfs reads, provider-file parsing, database mirroring, or filesystem watching.
- Replacing the CLI, M2 `inspect`, native recovery tools, acpx, Pi, or Claude.
- Provider-specific state, optional adapter implementation, or automatic provider discovery.
- Prompt generation, model-based summarization, decision extraction, autonomous recommendations, or external API calls.
- Hosted, remote, multi-user, multi-tenant, or cross-home aggregation.
- Claiming complete chronology, attempts, blockers, decisions, causality, or staleness from fields that do not exist.
- M7 routing or workflow automation.
- Treating logs as an event store, audit ledger, recovery source, repair input, or replacement for durable records.
- Remote log shipping, telemetry, analytics, system-wide collection, or default persistent logging.

## Related

- [Implementation plan](./implementation-plan.md)
- [CLI-first delivery plan](./cli-first-delivery-plan.md)
- [v0.x CLI](../surfaces/cli.md)
- [CLI multi-turn operator readiness](../validation/cli-multiturn-operator-readiness.md)
- [Durable store contract](../../architecture/contracts/durable-store.md)
- [Product architecture](../../architecture/product-architecture.md)
- [Contract conventions](../../architecture/contracts/conventions.md)
- [Technology stack](../scope/technology-stack.md)
- [Testing and agent workflow](../engineering/testing-and-agent-workflow.md)
- [Native session recovery](../../playbooks/native-session-recovery.md)
