---
name: product_architecture
description: "Target architecture for zxro as a durable work-address and mailbox layer around external agent runtimes."
type: architecture
tags: [architecture, target-state, zxro]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:54:00+08:00
---

# Product architecture

## Product thesis

zxro keeps durable identities and artifacts for agent-coordinated work. It does not run language models, own coding-agent conversations, or decide what work should happen next. A human or watchtower can address a stable work item while the underlying coding session is created, resumed, replaced, or inspected through another tool.

The first use case is a Pi watchtower coordinating several Pi and Claude crews through ACP/acpx. The same watchtower may coordinate work in several repositories or worktrees at once.

## System boundary

zxro owns:

- watchtower identities and their project directories;
- work identities that survive multiple crew turns;
- turn identities for individual delegated executions;
- durable turn results and lifecycle events;
- per-watchtower inbox generations and acknowledgements;
- metadata propagation through `ZXRO_*` environment variables.

zxro does not own:

- agent process hosting or conversation persistence;
- ACP protocol implementation;
- model selection, tools, permissions, or context management inside a coding harness;
- worktree creation, branch policy, review policy, testing policy, or merge policy;
- task decomposition, prioritization, or routing decisions.

For v0.x, acpx owns the agent-session layer. Pi and Claude own their native execution behavior. The watchtower owns routing decisions.

## Architectural principles

- Durable identity is independent from native session identity. `work_id` must not be derived from a cwd, process ID, or provider session ID.
- Metadata stays outside the model conversation. zxro passes identity through environment variables and persists the authoritative record on disk.
- The watchtower project and the crew target are separate directories. A watchtower loads its own `AGENTS.md`, skills, prompts, and settings from its project cwd. Each crew turn has an independent target cwd.
- Multiple watchtowers may share one `$ZXRO_HOME`. Use separate homes when operators, companies, customers, or experiments must not share durable zxro state.
- Integrations reduce to CLI operations. Pi extensions, Claude hooks, CI jobs, and humans must be able to produce the same durable state through documented zxro commands.
- Durable state is written before a best-effort wake or notification. A lost wake must not lose the work result.
- Reconciliation cost is bounded by new information, not task age. Routine inbox and inspection commands must not replay accumulated reports, transcripts, logs, or prior turn payloads.
- Context is progressively disclosed. Watchtowers first receive small event envelopes, then fetch current work state, turn metadata, or referenced artifacts only when the routing decision needs more evidence.
- Native session recovery is a last resort. zxro records enough session metadata to help an operator find and resume the underlying Pi or Claude conversation without making native session formats part of the zxro contract.

## Major capabilities

| Capability | Responsibility | Owner |
|---|---|---|
| Watchtower registry | Map a stable watchtower ID to its orchestration project cwd and optional runtime session address | zxro |
| Work registry | Keep a stable logical work ID across coder, reviewer, tester, and follow-up turns | zxro |
| Turn ledger | Record one delegated execution, target cwd, agent, session address, state, bounded summary, and artifact references | zxro |
| Artifact store | Keep potentially large per-turn reports, logs, and evidence separate from routine reconciliation records | zxro |
| Inbox | Append ordered, bounded work events for a watchtower and expose only pending generations by default | zxro |
| Acknowledgement | Record the highest inbox generation the watchtower has consumed | zxro |
| Agent sessions | Create, persist, queue, resume, and cancel coding-agent conversations | acpx / ACP agent |
| Agent lifecycle | Produce native completion signals such as Pi `agent_settled` or Claude `Stop` | coding harness |
| Routing | Decide which crew or operator should act next | watchtower / human |

## End-to-end flow

```mermaid
flowchart LR
    O[Operator] --> W[Pi watchtower project]
    W --> Z[zxro CLI]
    Z --> A[acpx]
    A --> C1[Claude or Pi crew]
    C1 --> H[Native completion hook]
    H --> Z2[zxro turn settle]
    Z2 --> I[Durable watchtower inbox]
    I --> W2[Watchtower reconcile]
    W2 --> Z
```

A typical work item may move through several persistent crew sessions:

```text
work: auth-fix
  coder-auth turn 1
  reviewer-auth turn 1
  coder-auth turn 2
  tester-auth turn 1
  done
```

The `work_id` stays stable. Every delegated execution gets a new `turn_id`. Crew session names may be reused when follow-up work should keep conversation context.

## Progressive context disclosure

A long-running work item must not become more expensive to reconcile just because it has accumulated history. zxro separates routing data from evidence so the watchtower can read only as deep as the current decision requires.

The default read path is:

```text
Level 0  zxro inbox pending
         new bounded event envelopes only

Level 1  zxro work show <work-id>
         current state, latest bounded summary, current references

Level 2  zxro turn show <turn-id>
         one turn's metadata, outcome, bounded summary, artifact references

Level 3  zxro artifact path <artifact-ref>
         local path to the full report, log, diff, or evidence
         inspect with grep, sed, tail, or another deliberate reader
```

Routine commands must not inline artifact contents. They may return references, byte sizes, media/type hints, and bounded summaries.

A settled turn therefore produces two different things:

1. A small inbox event used for routing.
2. Zero or more referenced artifacts used only when deeper inspection is necessary.

Example inbox event:

```json
{
  "generation": 17,
  "type": "turn_settled",
  "watchtower_id": "main",
  "work_id": "auth-fix",
  "turn_id": "550e8400-e29b-41d4-a716-446655440000",
  "outcome": "completed",
  "summary": "Reviewer found one blocker in refresh-token expiry handling.",
  "artifacts": [
    {
      "ref": "turns/550e8400-e29b-41d4-a716-446655440000/review.md",
      "kind": "review",
      "bytes": 8921
    }
  ]
}
```

The event summary is routing context, not a handoff document. v0.x limits summaries to 1,000 Unicode characters after normalization. Larger material belongs in an artifact.

zxro must not maintain one append-only handoff document whose full contents are expected to be read on every update. Each turn owns its own result and artifacts. Work records point at current or relevant turns without copying their accumulated contents.

This gives zxro a practical context-cost invariant:

```text
routine reconciliation cost ~= new pending events
```

not:

```text
routine reconciliation cost ~= complete work history x number of reconciliations
```

## Watchtower and crew cwd

A watchtower has a dedicated project directory, for example:

```text
~/watchtowers/main/
├── AGENTS.md
├── .pi/
│   ├── skills/
│   └── prompts/
└── ...
```

The watchtower session runs from that directory. Its crews may operate anywhere else:

```text
main watchtower
├── ~/src/rozoro-wt/pr-63     Claude coder
├── ~/src/xatu-wt/auth        Pi scout
└── ~/src/another-repo        Claude reviewer
```

`watchtower.cwd` is the orchestration project. `turn.cwd` is the crew target. zxro must never infer one from the other.

## Multiple watchtowers and isolation

A zxro home is one durable-state and trust boundary. It may contain several watchtowers when sharing state is intentional:

```text
$ZXRO_HOME
├── watchtower: alice
├── watchtower: bob
└── watchtower: release
```

Separate companies, customers, operators, or experiments that must not share zxro state should use separate homes:

```text
~/.zxro/acme/
~/.zxro/contoso/
~/.zxro/personal/
```

zxro does not model companies or organizations as domain objects in v0.x. The filesystem root provides that separation without adding organizational semantics to work and watchtower identities.

## Integration posture

| External system | Purpose | Direction | Failure posture |
|---|---|---|---|
| acpx | Persistent ACP sessions and agent transport | zxro/operator -> acpx | zxro records no runtime claim it cannot verify; native recovery remains available |
| Pi | Watchtower and crew agent | bidirectional through acpx; later native extension -> zxro | `agent_settled` integration is optional until the CLI contract is proven |
| Claude Code | Crew agent | bidirectional through acpx; later hook -> zxro | `Stop`/failure integration is optional until the CLI contract is proven |
| Unix filesystem | Durable zxro records and artifacts | zxro read/write | fail closed on malformed, unsafe, or conflicting state |

## Data and trust boundaries

`$ZXRO_HOME`, defaulting to `~/.zxro`, is authoritative for zxro identity and mailbox state. Native agent stores remain authoritative for their own conversation transcripts.

One `$ZXRO_HOME` may contain several cooperating watchtowers. Separate homes are the v0.x isolation mechanism when durable state must not cross an operator, company, customer, or experimental boundary.

zxro must not store provider credentials. Child processes may inherit provider-specific environment variables, but zxro only persists the names of metadata variables it owns and non-secret session references needed for recovery.

## Non-goals

- A new agent framework or ACP implementation.
- A daemon, scheduler, web service, or database in v0.x.
- Replacing acpx session persistence.
- Replacing Pi or Claude native session formats.
- Making a watchtower continuously resident. A watchtower may be a persistent conversation that wakes for discrete turns.
- Automatically loading complete work history into an agent context.
- Treating zxro artifacts as prompts. Artifacts are evidence that consumers fetch deliberately.

## Related

- [Ubiquitous language](./ubiquitous-language.md)
- [v0.x goal and scope](../v0.x/scope/goal-and-scope.md)
- [v0.x CLI](../v0.x/surfaces/cli.md)
- [Native session recovery](../playbooks/native-session-recovery.md)
