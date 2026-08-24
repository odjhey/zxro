#!/usr/bin/env node
// Query Markdown documents by YAML frontmatter. Zero dependencies (Node 18+).
//
// Usage:
//   node docs/scripts/find-docs.mjs
//   node docs/scripts/find-docs.mjs --type contract
//   node docs/scripts/find-docs.mjs --tag v0.x --tag engineering
//   node docs/scripts/find-docs.mjs --name product_architecture
//   node docs/scripts/find-docs.mjs runtime provisioning
//   node docs/scripts/find-docs.mjs --all
//   node docs/scripts/find-docs.mjs --stale
//   node docs/scripts/find-docs.mjs --status archived
//   node docs/scripts/find-docs.mjs --json
//
// Stale documents are archived, superseded, or past stale_after. They are hidden
// by default. Exit codes: 0 for matches, 1 for no matches, 2 for invalid usage.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_FILE = fileURLToPath(import.meta.url)
const DOCS_ROOT = resolve(dirname(SCRIPT_FILE), '..')

function* markdownFiles(directory) {
  for (const entry of readdirSync(directory).sort()) {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) yield* markdownFiles(path)
    else if (entry.endsWith('.md')) yield path
  }
}

function parseFrontmatter(text) {
  if (!text.startsWith('---\n')) return null
  const end = text.indexOf('\n---', 4)
  if (end === -1) return null

  const frontmatter = {}
  for (const line of text.slice(4, end).split('\n')) {
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*):\s+(.*)$/)
    if (!match) continue

    let [, key, value] = match
    value = value.trim()
    if (value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1).replace(/\\"/g, '"')
    }
    if (value.startsWith('[') && value.endsWith(']')) {
      frontmatter[key] = value
        .slice(1, -1)
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    } else {
      frontmatter[key] = value
    }
  }
  return frontmatter
}

const args = process.argv.slice(2)
const filters = { type: [], tag: [], status: [], name: [] }
const terms = []
let staleOnly = false
let includeAll = false
let json = false

for (let index = 0; index < args.length; index += 1) {
  const argument = args[index]
  if (argument === '--stale') staleOnly = true
  else if (argument === '--all') includeAll = true
  else if (argument === '--json') json = true
  else if (argument === '--help' || argument === '-h') {
    const help = readFileSync(SCRIPT_FILE, 'utf8')
      .split('\n')
      .filter((line) => line.startsWith('//'))
      .map((line) => line.replace(/^\/\/ ?/, ''))
      .join('\n')
    console.log(help)
    process.exit(0)
  } else if (argument.startsWith('--')) {
    const key = argument.slice(2)
    if (!(key in filters)) {
      console.error(`unknown flag: ${argument}`)
      process.exit(2)
    }
    const value = args[index + 1]
    if (!value || value.startsWith('--')) {
      console.error(`missing value for ${argument}`)
      process.exit(2)
    }
    filters[key].push(value)
    index += 1
  } else {
    terms.push(argument.toLowerCase())
  }
}

const today = new Date().toISOString().slice(0, 10)
const documents = []

for (const file of markdownFiles(DOCS_ROOT)) {
  const frontmatter = parseFrontmatter(readFileSync(file, 'utf8'))
  if (!frontmatter?.name) continue

  const tags = frontmatter.tags ?? []
  const isStale =
    frontmatter.status === 'archived' ||
    frontmatter.status === 'superseded' ||
    Boolean(frontmatter.stale_after && frontmatter.stale_after.slice(0, 10) < today)

  if (staleOnly && !isStale) continue
  if (!staleOnly && !includeAll && !filters.status.length && isStale) continue
  if (filters.type.length && !filters.type.includes(frontmatter.type)) continue
  if (filters.status.length && !filters.status.includes(frontmatter.status)) continue
  if (filters.name.length && !filters.name.includes(frontmatter.name)) continue
  if (filters.tag.length && !filters.tag.every((tag) => tags.includes(tag))) continue

  if (terms.length) {
    const searchable = `${frontmatter.name} ${frontmatter.description ?? ''} ${tags.join(' ')}`.toLowerCase()
    if (!terms.every((term) => searchable.includes(term))) continue
  }

  documents.push({
    path: relative(DOCS_ROOT, file),
    ...frontmatter,
    stale: isStale,
  })
}

documents.sort((left, right) => left.path.localeCompare(right.path))

if (json) {
  console.log(JSON.stringify(documents, null, 2))
} else {
  for (const document of documents) {
    console.log(`${document.path}${document.stale ? ' [STALE]' : ''}`)
    console.log(
      `  ${document.type ?? '?'} · ${document.name}${document.tags?.length ? ` · ${document.tags.join(', ')}` : ''}`,
    )
    console.log(`  ${document.description ?? ''}`)
  }
  console.error(`\n${documents.length} doc(s)`)
}

process.exit(documents.length ? 0 : 1)
