# Curated metadata and filtered retrieval

Refs #3, #8; prerequisite for viewer catalog #29 and facets #31. This increment adds storage and
retrieval contracts, not a visual UI or the complete contextual ranking feature.

## Note capture

Optional fields on an ordinary note candidate:

```json
{
  "tags": ["python", "windows"],
  "project": "second-brain",
  "source_refs": ["docs/example.md"],
  "related": ["example-note"],
  "sensitivity": "private"
}
```

Supply these alongside the required note fields, not as a standalone capture. Each list has at
most 20 nonempty strings. Tags are trimmed, case-folded and deduplicated (max 100 characters).
Related entries are stable note IDs, not arbitrary paths; they may name not-yet-created notes.
References are inert text (max 500 characters), never automatically resolved or fetched.
Project is a lowercase slug (max 100 characters) or null. Sensitivity is normal/restricted/private;
it describes content and does not grant an ACL or certify privacy. Secret rejection still applies.

Omitted fields retain prior values when a note is updated. Empty lists explicitly clear list
fields; null clears project. Existing notes without project remain readable and unassigned.
Invalid metadata is rejected before writing, including on read after filesystem tampering.
Revision archives retain prior metadata. Event fingerprints and ledger entries are unchanged;
metadata remains in Markdown, not in the ledger. Journal-only payloads retain their six-field schema.

## Retrieval

CLI: `second-brain search 'git' --tag windows --tag python --project second-brain --type command
--status verified --source-agent codex` (one command). Repeated tags require all tags; match is
exact after normalization. Project and enum facets match exactly. Missing facets impose no filter.

MCP: `search_memory(query="git", filters={"tags":["windows"], "project":"second-brain"})`.
Use tags=[] to select untagged notes or project=null for unassigned notes through MCP/core.
Unknown fields and invalid filter values fail closed. Empty query allows bounded browsing.
Search returns up to five notes. Local CLI and stdio search use the configured vault.
Exact IDs rank first, followed by exact titles/tags and literal phrases, then lexical coverage
and SQLite FTS5 rank. Paste a command, IP or path as written. Partial hits can follow the
literal match. FTS5 also matches text such as `revision` against `revisión`. Exact tags
and other filters still decide which notes are eligible.

The index lives in the search process. Shiori reads current canonical notes before reuse
and rebuilds the index after changes. When SQLite lacks FTS5, literal and lexical search
still work. Archives and journal entries remain outside canonical note search.
Basic Memory is available for an explicit local diagnostic search with
`search_memory(query="git", engine="basic-memory")`.

### Context and links

Local `get_context` and CLI `context` return verbatim excerpts and one-hop relationships.
Follow `related_note_ids` to notes or decisions the result links to and `backlink_note_ids`
to notes that link back. Read the target with `read_memory` or CLI `read`. Follow `task_keys`
with `get_work_context` or CLI `task`. Links come from the current profile's note metadata
and task pages. Each relation list has a maximum of five IDs and shares the context budget.

`retrieval_state` is `verified` for notes with evidence and a valid verification date less
than 90 days old, `historical` for obsolete or superseded notes, and `needs-revalidation`
otherwise. Read the warnings and verification date before acting. Ordinary search can return
historical notes. Context hides them by default and accepts an exact status filter to inspect them.
Task context reports the same states for explicitly linked notes.

### Local benchmark

Two runs per revision on Windows with Python 3.12 used 1,000 synthetic notes in a disposable
vault. Each run queried an IP, a command, a path, an unaccented word, a decision ID and a
two-word operation. The IP, command and path had deliberately similar distractors. Timings
include reading and validating notes, ranking and assembling the context. The warm median
excludes the first query in each process.

| Measurement | Previous ranking | Local search |
|---|---:|---:|
| Expected note first | 2 of 6 | 6 of 6 |
| Expected note in first five | 5 of 6 | 6 of 6 |
| First query | 4.31–4.79 s | 2.51 s |
| Warm median per run | 2.86–2.88 s | 0.58–0.59 s |

The sample covers literal and lexical retrieval. Queries phrased as paraphrases may require a
semantic index. Keep it optional and revisit it once representative searches show how often
that gap matters. See the [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html).

## Compatibility and evidence — 2026-10-16

The initial round-trip test failed because supplied tags were silently replaced by an empty list.
Local suite after implementation: 64 passed, one native-symlink privilege skip; Ruff passed.
Tests cover normalization, explicit clearing, omitted-field preservation, revision history,
invalid/secret/tampered metadata, combined exact facets, empty queries and unknown-field rejection.
CLI subprocess capture/search passes. MCP capture/read/filter tests include a provider returning
an out-of-filter result; that result never enters the filtered response.

Existing Codex MCP processes may retain old imports. Until a fresh server exposes these tool
parameters, use the updated CLI for filtered reads and note captures. An old writer can discard
new metadata; the skill explicitly routes those operations to the CLI. No migration, restart,
work activation, content upload or edit of existing personal notes is required by this PR.
