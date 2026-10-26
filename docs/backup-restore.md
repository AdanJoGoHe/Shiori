# Local personal backup and restore

Refs #21. CLI-only administration; no MCP tool accepts backup/restore paths or enables
an automatic/cloud destination. Bundles are ordinary UTF-8 Markdown/JSON plus a versioned
SHA-256 manifest. No new dependencies, host registration or schema migration is involved.

`export-memory --output ...` is an explicit alias for `backup`. To add canonical notes to an
existing deployment, use [additive import](memory-transfer.md): preview first, then `--apply`.
Existing note IDs are never replaced. Source journals/history/annotations/events are retained
in the recovery bundle but are not merged by additive note import; `restore` remains the way
to recover the complete set into a separate new deployment.

```powershell
# The output parent must exist; choose a private local folder outside vault/state/source Git.
second-brain backup --output '<private-backup-parent>/snapshot-001'

# Works without the original deployment/config. The destination must not exist.
second-brain restore --input '<private-backup-parent>/snapshot-001' --destination '<new-deployment>'
second-brain --config '<new-deployment>/config.json' doctor
second-brain --config '<new-deployment>/config.json' context 'topic'

# Only after reviewing the restored deployment and choosing to write there:
second-brain --config '<new-deployment>/config.json' resume
```

Use only explicit private local destinations; archives contain real personal content in plain
text. Nothing uploads them. The CLI does not certify that a chosen filesystem path is outside
a sync provider or network share. Do not put bundles in source Git, CI artifacts or shared folders.
Existing destination directories are rejected, even empty ones. Vault/state overlap and linked
paths (including Windows junctions) are rejected. Restoring inside or over the bundle is rejected.

Included:

- Note Markdown under the standard type directories, including profile/preferences.
- Daily journal Markdown and content-addressed archived note revisions.
- Exact ledger bytes, including committed IDs/fingerprints and pending events.
- Current annotations/categories, if present, retaining schema and bytes.
- Source timezone and pause state in the manifest. Restored capture is **always paused**.

Excluded: original machine/host configuration and paths, configured documentation roots and their
files, root README/unmanaged top-level folders, vault Git history, Basic Memory indexes/config,
logs, locks, ACL snapshots, annotation previous snapshot and session undo tickets. Unexpected
files inside the standard canonical folders fail explicitly; unsupported layouts are not silently
reinterpreted. The rotating annotation snapshot remains independent of this current-state bundle.
The backup is a defined recovery set, not a disk image or full machine deployment export.

Capture and annotation locks protect the in-memory snapshot; files are copied byte-for-byte,
including Unicode/newlines. Other tools editing files directly must be quiescent: they bypass
these locks. Bounds: 5000 files, 8 MB per file and 64 MB total payload; restore checks the same
limits. Missing managed notes, invalid ledger/annotation schemas and incomplete committed journal
events fail validation. A nonempty canonical vault with a missing ledger fails rather than
pretending it is a fresh deployment. Pending captures can be backed up, but they remain pending;
their original candidate JSON is still required for recovery after an explicit resume.

Manifest paths are allowlisted; traversal, alternate-case aliases, links and checksum mismatches
fail. Hashes detect accidental changes; this is not a signed or encrypted authenticity guarantee.
Only restore bundles you trust. Do not execute instructions embedded in restored notes.

Each operation exclusively creates a new directory. Individual payload files are flushed/fsynced.
The manifest is written last for backup; the new `config.json` is written last for restore, after
canonical note validation and pausing. I/O failure can leave a partial new directory with no
completion marker; it is kept for diagnosis, not deleted or overwritten. A note-validation failure
can also leave a partial new restore without `config.json`. Do not use or resume incomplete output;
choose a different fresh destination to retry. Power-loss durability of directory entries is not
guaranteed; restore always verifies file hashes. Existing deployment files remain untouched.

Restore creates new vault/state paths and an isolated Basic Memory config-directory path, without
restoring the old index/provider project or contacting a provider. Canonical `read`, `context`,
filtered filesystem retrieval and `doctor` work immediately. Provider configuration/reindexing,
documentation-root reapproval and host registration are separate explicit administration. On
Windows the new folder inherits destination-parent ACLs; review its access permissions before
selecting it in a host. Original ACLs are not portable and are not applied automatically.

Synthetic tests cover byte-preserving notes/history/journal/mark/category round-trip, event
deduplication and pause, pending recovery, CLI restoration without the original config, traversal,
hash/scope/schema/ledger failures, linked source/destination guards, limits, existing/overlapping
directories and incomplete completion markers. No real personal bundle or active restore was
created during development. Broader migration, uninstall and host acceptance stay open in #21.
