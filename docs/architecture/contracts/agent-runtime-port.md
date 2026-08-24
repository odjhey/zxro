---
name: agent_runtime_port_contract
description: "Semantic port between zxro/watchtower logic and external agent runtimes, including DATA, CONTROL, status, start, and exact resume behavior."
type: contract
tags: [architecture, contracts, runtime, ports, acpx]
status: draft
generated: "ChatGPT GPT-5.6 Sol, 2026-08-24"
sources:
  - ref: https://github.com/odjhey/rozoro/blob/master/bin/rzr-send.sh
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/blob/master/bin/rzr-control.sh
    credibility: primary
  - ref: https://github.com/odjhey/rozoro/blob/master/bin/rzr-resume.sh
    credibility: primary
created_at: 2026-08-24T16:41:00+08:00
updated_at: 2026-08-24T16:41:00+08:00
---

# Agent runtime port

## Purpose

zxro owns durable work addresses and mailbox state. It does not own the coding-agent runtime. Still, watchtowers and future integrations need a stable vocabulary for what they ask an external runtime to do.

This document defines that **semantic port**. It is intentionally smaller than Rozoro's current runtime surface and intentionally does not require zxro to proxy acpx or native harness commands.

## This is not a network port

`port` here means an architecture boundary, not a TCP/UDP port number.

zxro v0.x opens no TCP listener, UDP listener, or Unix-domain socket. acpx may use its own transport and ACP may use stdio or another mechanism; those are runtime-adapter details.

If zxro later gains a Unix socket or daemon, that transport must implement the same semantic contracts rather than creating a second state model.

## Runtime operations

A runtime adapter may expose the semantic equivalent of:

```text
runtime.start(turn, initial_input?) -> session binding
runtime.describe(binding) -> runtime state + capabilities
runtime.send(binding, text) -> delivery result
runtime.control(binding, action) -> control result
runtime.resume(binding, followup?) -> same conversation
runtime.stop(binding) -> runtime result
```

The first expected adapter is acpx. v0.x may call acpx directly from a human or watchtower instead of implementing these operations inside zxro.

## Start

`start` begins a new external execution for an already-created zxro turn.

Requirements:

- the zxro turn exists before runtime start;
- start does not silently create work or a turn;
- the returned session address may enrich the turn's durable [session binding](./session-binding.md);
- failure to launch does not manufacture a zxro settlement;
- starting a replacement conversation for the same logical work uses a new turn.

This is why zxro should not copy Rozoro's all-in-one `start = reserve + render + spawn + link` command as its core boundary. Durable creation and runtime launch are separate operations.

## DATA plane

`send` is free text intended for the agent to read and reason about.

```text
DATA(text) -> agent conversation
```

Rules:

- payload is model-visible content;
- sending text never means interrupt, cancel, stop, or another runtime action;
- adapters must not reinterpret a magic sentence as a CONTROL command;
- a failed or ambiguous target fails closed rather than guessing another session.

Rozoro's explicit `send`/`control` split is worth preserving as a port invariant even though zxro does not need Rozoro's Herdr implementation.

## CONTROL plane

`control` executes a closed runtime action. It is not chat.

```text
CONTROL(interrupt)
CONTROL(cancel)
CONTROL(stop)
```

An adapter may support only a subset. Unsupported actions fail explicitly.

The generic contract does **not** include arbitrary key presses or shell commands. Those are host-specific escape hatches, not portable runtime semantics.

A control request must never be delivered to the model as text merely because the adapter cannot execute it.

## Start, resume, and replacement are different

These operations must not collapse into one convenient fallback:

```text
start new       new conversation for a new turn
resume exact    same recorded conversation
replace         new turn + new conversation
```

`resume` requires a valid session binding and a runtime capability that supports exact continuation. If the identity is missing, ambiguous, or unsupported, fail. Do not cold-start and call it resume.

A Rozoro-style `restart` that tears down hosting and creates a new conversation mixes runtime lifecycle with durable task semantics. zxro should not make that a core runtime verb. A client that wants a new conversation creates a new turn and calls `start`.

## Describe/status

Runtime status answers runtime questions only, for example:

```text
reachable
working
idle/quiescent
blocked
stopped
gone
unknown
```

Exact states are adapter-specific; the portable rule is more important:

> runtime status is not work acceptance.

A runtime becoming idle, stopped, or gone must not close work, handle a mailbox event, or manufacture a successful settlement.

Harness-native semantic completion is the source that may trigger `zxro turn settle`. Host/process liveness remains supporting evidence.

## Durable command boundary

The zxro CLI remains the durable ingress:

```text
zxro work create
zxro turn create
zxro turn bind        # enrich external session identity
zxro turn settle
zxro inbox unread
zxro inbox pending
zxro inbox handle
zxro ack
```

The runtime port remains outside zxro in v0.x:

```text
watchtower / human
       |
   acpx or native adapter
       |
  coding harness
```

There is no need to add `zxro send`, `zxro control`, or `zxro resume` merely to wrap acpx. Add a zxro runtime proxy only if a concrete integration problem requires one. If such commands are added later, they must preserve the DATA/CONTROL/exact-resume semantics in this contract.

## Completion ingress

A runtime adapter does not write zxro provider files directly. On a trustworthy harness completion boundary it invokes the same public durable command as a human:

```sh
zxro turn settle <turn-id> ...
```

Retries use zxro's settlement idempotency. Adapter-local retry custody may exist if a hook can crash before invoking zxro, but that custody belongs to the adapter and must not create a second zxro event model.

## Late runtime traffic

A delayed status or lifecycle message may update evidence for an existing turn, but it cannot implicitly:

- reopen closed work;
- create a new turn;
- mark attention handled;
- change operator acceptance.

This is the zxro version of the lifecycle-membership bug Rozoro later had to fix: runtime traffic must not resurrect retired logical work.

## Failure posture

- Unknown or ambiguous session target: fail closed.
- Unsupported runtime action: fail explicitly.
- Lost DATA delivery with uncertain outcome: do not claim success.
- Failed CONTROL action: do not replace it with chat text.
- Missing exact-resume capability: fail rather than start cold.
- Runtime status unavailable: return unknown/unavailable rather than inferring completion.

## Related

- [Session binding](./session-binding.md)
- [Durable store](./durable-store.md)
- [Product architecture](../product-architecture.md)
- [Runtime and provisioning](../../v0.x/engineering/runtime-and-provisioning.md)
