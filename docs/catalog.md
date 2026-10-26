# Read-only content catalog

Refs #29 (SB-027), parent #27. This is the metadata/listing foundation for the visual explorer;
it does not implement a browser UI, body-reading endpoint or document editing.

## Sources and access

The trusted personal deployment config may contain up to ten explicitly authorized roots:

```json
{"documentation_roots": {"second-brain-docs": "D:/repo/memory/docs"}}
```

Absent configuration means no documentation sources. Existing personal notes and journals are
still available as source `personal`. Configure narrow documentation directories, since approving
a root authorizes listing its Markdown metadata. Roots must be absolute, unlinked and must not
overlap the vault or state in either direction. Work deployments remain rejected by the core.
API requests select kind/source IDs; they cannot supply filesystem roots or arbitrary paths.

Documentation enumeration skips hidden names, archive(s), backups, runtime, local, node_modules
and __pycache__ directories, non-Markdown files and credentials/secrets/passwords/tokens.md files.
Symlinks/junctions are skipped and reported, including linked ancestors of a configured root.
These exclusions are additional guards, not sensitive-content classification: use narrow trusted
roots and curated files. No raw content or OS exception text is emitted in diagnostics.

Notes must be ledger-managed and located in canonical note folders. The core validates each note
and its metadata. Journals are only files matching journal/YYYY/YYYY-MM-DD.md and valid calendar
dates; they are not indexed as canonical knowledge. No archive, index or state collection exists.

## API and limits

CLI: `second-brain catalog --kind documentation --source second-brain-docs --offset 0 --limit 25`.
MCP: `list_content(kind="documentation", source="second-brain-docs", offset=0, limit=25)`.
Both return items, next_offset, errors, truncated and additive diagnostics. Omit kind/source to combine approved sources.
Diagnostics include collection health, registered/readable note counts and an opaque store ID;
see [error states and CLI/MCP/HTTP parity](catalog-diagnostics.md). A truncated or partially failed
listing cannot establish that a missing result does not exist.
Limits: 1–100 rows per page, at most 2,000 scanned entries across sources and 1 MB per file.
Directory scanning uses an explicit stack and the entry budget; errors are deduplicated/capped.
If truncated is true, narrow kind/source or configure smaller roots; next_offset cannot recover
entries beyond the scan budget. The ledger itself retains the existing core loading behavior.

Each row contains ID, kind, source, relative path, title, timestamps and available metadata.
Missing metadata is null, distinct from a known empty tag list. Note timestamps come from validated
frontmatter; documentation/journal update time comes from filesystem mtime and creation time is
unknown. Documentation titles use frontmatter title, first H1, then filename. Bodies are not returned.
References stay inert; listing does not render HTML, execute instructions or fetch external URLs.

Rows sort by kind/source/path. Note IDs use the canonical note ID; document/journal IDs use source
and relative path, so changing a heading retains ID while moving a file changes it. Every call
reads current files; offset paging is not a snapshot under concurrent changes. Refresh from zero
after changes. Missing/inaccessible/invalid sources yield redacted per-source errors and healthy
sources continue. Inspect both errors and truncated before claiming a complete inventory.

## Verification

Synthetic tests cover source separation, metadata, pagination, refresh/delete, byte-preserving
reads, unmanaged/excluded files, invalid content, missing and overlapping roots, scan truncation,
bad requests and Windows junction escape. CLI listing and an independent stdio MCP process also
exercise the boundary. This is catalog protocol evidence, not a completed real-browser viewer test.
Existing MCP processes may not expose list_content until restarted; the CLI loads current code.

Actual documentation exposed a Windows redirected-output incompatibility (cp1252 em dash bytes
read as UTF-8). CLI stdout/stderr now explicitly use UTF-8. The CLI regression test forces a
cp1252 environment and verifies a Unicode document title through a UTF-8 subprocess consumer.

The actual personal CLI subsequently listed configured project documentation, canonical notes
and dated journals without errors or truncation; ledger bytes were unchanged. The narrow docs
root was added to local config with a backup, and installed skill ownership/backups were checked.
Local final suite: 76 passed, one native-symlink privilege skip; Ruff and skill validation passed.
