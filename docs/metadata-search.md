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
The existing maximum of five results and deterministic score/ID ordering remain in force;
pagination, date facets and UI facet counts remain future viewer work.

Filtered MCP retrieval uses canonical files and does not consult Basic Memory ranking. This
keeps index rows from reintroducing notes excluded by a filter. Unfiltered retrieval retains
the existing provider/fallback path. Scope cannot be selected by a filter. Archives and journal
entries remain outside canonical note search.

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
