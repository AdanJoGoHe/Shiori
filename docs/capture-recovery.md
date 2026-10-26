# Capture recovery for agents

Refs #19. The ledger records event IDs, fingerprints, relative paths, timestamps and
pending/committed states. It never retains candidate bodies. No ledger schema migration is needed.

Keep the original candidate until `capture_memory` / CLI `capture --event-file` returns `saved`
or `duplicate`. On failure, retry the identical candidate with its original `event_id`.
Changing a payload while reusing that event ID is rejected, including for pending events.
Paused capture returns `skipped` and does not recover a pending event.

Inspect pending metadata using MCP `list_pending_captures(offset=0, limit=25)` or:

```powershell
second-brain pending --offset 0 --limit 25
second-brain capture --event-file '<original-candidate.json>'
```

Pages accept nonnegative offsets and limits of 1–100. Results contain `events`, `total`,
`next_offset` and retry guidance. Each event exposes only `event_id`, `status`, `fingerprint`,
`path` and `at`. Ordering follows ledger insertion. Each page is a locked snapshot; captures
between page requests can change offsets, so restart enumeration if the count changes.
Listing is read-only and still works while capture is paused. New MCP tools require a fresh
server process; the CLI loads current source immediately.

A new event targeting a note with an earlier pending capture returns:

```json
{"status":"blocked","reason":"pending-note-capture","id":"example","event_id":"earlier-event"}
```

This result makes no writes. Recover the named earlier event before submitting the new one.
The guard uses the stable note ID across all note type directories, including legacy pending
records without a note-ID field. Different notes and journal-only captures can continue;
sharing the same daily journal does not block them. Capture's existing deployment lock
serializes the pending check and writes across processes.

A persisted pending event retains its original timestamp and journal date across retries
and process restarts. Journal event markers and content-addressed history prevent duplicates.
If the initial pending-ledger write itself failed, there is no persisted event timestamp;
the retry begins at its new time. Individual files use atomic replacement, but the note,
journal and ledger are not a single transaction: partial canonical writes can be visible
before recovery completes. Older binaries bypass the new same-note guard; use updated
writers together. No payload queue, automatic retries, cancellation or lost-payload recovery
is introduced. If the original JSON is unavailable, do not invent it from excerpts or edit
the ledger to pretend the capture completed; manual recovery remains outside this increment.

Synthetic validation covers failures at pending-ledger, note, journal and commit writes for
new and updated notes; fresh-process retry after midnight; unchanged metadata and single
history/journal entries; same-ID/type-change blocking without writes; unrelated captures;
pause and changed-payload rejection; legacy pending pagination; MCP, fresh stdio discovery
and CLI parity. No existing personal pending event is retried or modified by these tests.
