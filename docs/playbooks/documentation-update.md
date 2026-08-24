---
name: documentation_update_playbook
description: "Procedure for keeping terminology, architecture, contracts, diagrams, plans, and indexes aligned with a change."
type: guide
tags: [playbooks, docs, architecture]
status: current
created_at: 2026-08-24T15:13:40+08:00
updated_at: 2026-08-24T15:24:31+08:00
---

# Documentation Update Playbook

## Trigger

Use this playbook when a change affects domain behavior, terminology, ownership boundaries, interfaces, major flows, or operating expectations.

## Procedure

1. Identify the authoritative document for the changed concept.
2. Update terminology first when names or meanings changed.
3. Update bounded contexts and contracts when ownership or interfaces changed.
4. Update architecture prose before diagrams.
5. Update v0.x plans, task cards, and checklists when delivery impact changed.
6. Bump `updated_at` on materially changed documents.
7. Update the nearest directory index and [docs/INDEX.md](../INDEX.md) for added or moved files.
8. Check links and query metadata.

## Verification

```sh
node docs/scripts/find-docs.mjs --all
# Add the repository's Markdown link checker when available.
```

## No-impact record

If no documentation update is needed, record why in the task or change summary.

## Related

- [Docs-and-writing skill](../../.agents/skills/docs-and-writing/SKILL.md)
- [Find-docs skill](../../.agents/skills/find-docs/SKILL.md)
- [Documentation guide](../README.md)
- [Ubiquitous language](../architecture/ubiquitous-language.md)
- [Contracts](../architecture/contracts/README.md)
