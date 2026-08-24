---
name: find-docs
description: Find and filter project documentation by querying YAML frontmatter or scanning the docs index. Use when looking for architecture, contracts, plans, checklists, decisions, reports, or other knowledge under docs/.
---

# Finding Project Docs

All Markdown files under `docs/` carry frontmatter with at least `name`, `description`, and `type`. Schema details and trust fields are documented in `docs/README.md`. When creating or revising documentation, follow the companion [docs-and-writing skill](../docs-and-writing/SKILL.md) for the canonical template, house style, and maintenance workflow.

## Progressive discovery

1. Scan `docs/INDEX.md` for one-line descriptions.
2. Open the nearest directory `README.md`.
3. Follow links to specific documents.
4. Use the query script when filtering is faster.

## Query script

```sh
node docs/scripts/find-docs.mjs
node docs/scripts/find-docs.mjs --type contract
node docs/scripts/find-docs.mjs --tag v0.x --tag engineering
node docs/scripts/find-docs.mjs --name product_architecture
node docs/scripts/find-docs.mjs runtime provisioning
node docs/scripts/find-docs.mjs --all
node docs/scripts/find-docs.mjs --stale
node docs/scripts/find-docs.mjs --json
```

Multiple `--tag` values use AND semantics. Free-text terms must all occur across the name, description, or tags. The script exits with status 1 when nothing matches.

## Fallback searches

```sh
grep -rl --include='*.md' '^type: contract' docs/
grep -rl --include='*.md' '^name: product_architecture' docs/
grep -r --include='*.md' -l 'search text' docs/
```

## Trust and freshness

Before relying on a document:

- `status: archived` or `superseded` means historical only.
- A past `stale_after` requires re-verification.
- `generated` without `verified` is a recommendation, not human-confirmed truth.

Default queries hide stale documents. Use `--all` or `--stale` only when historical context matters.

## Type taxonomy

`index` | `architecture` | `bounded-context` | `contract` | `diagram` | `glossary` | `plan` | `spec` | `guide` | `checklist` | `reference` | `report` | `decision`

## Companion skill

After finding the authoritative document, use the [docs-and-writing skill](../docs-and-writing/SKILL.md) to create or edit it consistently.
