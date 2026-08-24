---
name: docs-and-writing
description: Create or revise project documentation using the repository frontmatter schema, house style, linking rules, indexes, and trust metadata. Use whenever writing, restructuring, reviewing, or materially editing Markdown under docs/.
---

# Documentation and Writing

Use this skill for every new or materially revised document under `docs/`. Use the companion [find-docs skill](../find-docs/SKILL.md) first to locate existing knowledge, avoid duplicate documents, and identify the nearest index.

## Required writing pass

Always apply the [unslop skill](../unslop/SKILL.md) before finalizing prose. Remove AI writing patterns without changing facts, requirements, canonical terms, code, or quoted source material. Technical accuracy takes priority when a style rewrite would alter meaning.

## Before writing

1. Read `docs/README.md` for the corpus layout and maintenance rules.
2. Use `node docs/scripts/find-docs.mjs <terms>` to find related documents.
3. Open the nearest directory `README.md` and the documents that own affected terminology or contracts.
4. Decide whether to update an existing document, add a new document, or record a decision. Prefer updating the existing source of truth.
5. Choose the document type and authoritative location before drafting.

## Canonical frontmatter template

Start every Markdown document under `docs/` with this template. Remove optional fields that do not apply; do not leave placeholder metadata.

```yaml
---
name: unique_snake_case_identifier
description: "One sentence describing the document's concrete contents."
type: index | architecture | bounded-context | contract | diagram | glossary | plan | spec | guide | checklist | reference | report | decision
tags: [area, topic]
status: draft | current | archived | superseded
created_at: "YYYY-MM-DDTHH:MM:SS+HH:MM"
updated_at: "YYYY-MM-DDTHH:MM:SS+HH:MM"
---
```

Optional fields:

```yaml
resource: path-or-url
generated: "agent or tool identity, session or date"
gate: 1
sources:
  - ref: path-or-url
    credibility: primary | secondary | inferred
verified: "reviewer identity and date"
stale_after: 2027-01-01
```

### Frontmatter rules

- `name` is globally unique, stable, lowercase `snake_case`, and independent of the title.
- `description` says what the document contains, not merely its topic. Keep it useful in search results.
- `type` reflects the document's function, not its directory.
- `tags` are lowercase, reusable search facets. Prefer existing tags; avoid near-synonyms.
- New substantive documents normally begin as `draft`; use `current` when accepted as the active source of truth.
- Set `generated` when an agent or tool originated substantive claims. Only a human reviewer adds `verified`.
- Use `sources` for claims that depend on external material or repository evidence.
- Set `stale_after` when correctness is time-sensitive.
- Preserve `created_at`; update `updated_at` after every material change. Use an ISO 8601 datetime with timezone.

## File and heading style

- Use lowercase kebab-case filenames, except directory indexes (`README.md`), the flat index (`INDEX.md`), and numbered decisions.
- Use one H1 matching the human-readable document title.
- Use sentence case for headings.
- Do not skip heading levels.
- Keep sections focused; split a document when it develops multiple owners or unrelated purposes.
- Use descriptive link text rather than “here” or raw paths.

## House style

- Write for a future contributor who lacks the current conversation's context.
- Lead with purpose, decision, or outcome; add background only when it changes interpretation.
- Prefer short, active, declarative sentences and concrete nouns.
- Use canonical terms from `docs/architecture/ubiquitous-language.md`. Do not introduce synonyms casually.
- Separate facts, decisions, assumptions, recommendations, and open questions.
- Use `must` for requirements, `should` for strong recommendations, and `may` for permission. Avoid ambiguous “will” when stating a requirement.
- State ownership, boundaries, failure behavior, and verification in testable terms.
- Avoid marketing language, filler, unexplained acronyms, and claims such as “simple,” “obvious,” or “easy.”
- Mark incomplete content explicitly with `TODO:` and describe what decision or evidence is missing.
- Prefer bullets for independent items, numbered lists for ordered procedures, and tables for comparable structured data.
- Add a language identifier to fenced code blocks. Use Mermaid for diagrams that should render in Markdown.
- Keep examples realistic but generic; never include secrets, tokens, personal data, or production credentials.

## Structure by document type

### Index

- State the area's purpose and boundaries.
- List every direct child with a one-line description.
- Give a reading order when sequence matters.
- Link back to the parent index.

### Architecture or bounded context

- Define purpose, ownership, boundaries, invariants, dependencies, flows, and non-goals.
- Link published interfaces to their contract documents.
- Keep target-state architecture distinct from v0.x delivery scope.

### Contract

- Name producers, consumers, and owner.
- Define language-neutral shapes, invariants, lifecycle, errors, compatibility, and examples.
- Describe migration impact when revising a published contract.

### Plan, specification, or checklist

- Define outcome, scope, dependencies, acceptance criteria, and verification evidence.
- Link durable behavior to architecture or contracts instead of duplicating it.
- Identify human gates and unresolved decisions explicitly.

### Decision

- Record context, options considered, choice, consequences, and durable rule.
- Explain why rejected options were not selected.
- Supersede prior decisions rather than rewriting their history.

### Report or reference

- Record provenance and date-sensitive assumptions.
- Distinguish observations from inference and recommendations.
- Use `generated`, `verified`, and `stale_after` when applicable.

## Links and progressive disclosure

- Use relative Markdown links within the repository.
- Every document must be linked from its nearest directory `README.md` and `docs/INDEX.md`.
- Add a `Related` section when it helps readers find prerequisites, source-of-truth documents, or next steps.
- A document no other document links to is an orphan and should be fixed.
- Diagrams summarize prose; they never become an independent source of behavior.
- Broken links to planned, not-yet-written material must be labeled explicitly rather than appearing accidental.

## Editing workflow

1. Find related documents with the [find-docs skill](../find-docs/SKILL.md).
2. Update the authoritative document first: terminology before dependent prose, contracts before diagrams, architecture before delivery plans.
3. Preserve useful history. Mark replaced documents `superseded` and link the replacement.
4. Update `updated_at` and trust metadata.
5. Add or update links in the nearest index and `docs/INDEX.md`.
6. Follow `docs/playbooks/documentation-update.md` when behavior, terminology, boundaries, or interfaces changed.

## Verification

Run at least:

```sh
node docs/scripts/find-docs.mjs --all
node docs/scripts/find-docs.mjs --name unique_snake_case_identifier
```

Then verify:

- frontmatter parses and names are unique;
- relative links resolve;
- the nearest index and `docs/INDEX.md` contain the document;
- terminology and contracts remain consistent;
- no stale or superseded document is presented as current;
- generated claims carry appropriate provenance;
- the final prose passes the [unslop](../unslop/SKILL.md) self-audit.

Use the [find-docs skill](../find-docs/SKILL.md) for query syntax, stale-document handling, and discovery fallback commands.
