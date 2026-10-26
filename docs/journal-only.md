# Journal-only capture

Refs #18 (one capture decision), #19 (deduplication/retry). This is a bounded increment;
it does not implement the full learning classifier, hook adapters or automatic recovery queue.

Use journal-only for meaningful task progress with no new reusable knowledge. The canonical
payload and invocation guidance live in [the skill](../skills/second-brain/SKILL.md).
The existing `capture --event-file` CLI and `capture_memory(candidate)` MCP accept the same object.
Missing mode preserves existing note capture behavior; unknown modes fail before writing.

Journal-only accepts exactly scope, mode, event_id, title, source_agent and summary. It requires
personal scope, a slug event ID, a known source agent, a nonempty title (max 200 characters)
and a nonempty summary (max 1000). Note fields are rejected to avoid silently dropping a lesson.
The secret filter runs before any write. Agents still minimize sensitive material themselves;
pattern detection does not certify arbitrary text as safe.

The response is `{"status":"saved","journal":"journal/YYYY/YYYY-MM-DD.md"}` or the same path
with status duplicate for an identical retry. No canonical note, archive revision or Knowledge
link is created. Search/read remain restricted to canonical notes. The ledger stores a fingerprint,
path, timestamp and transaction state, not the journal title or summary. Existing ledger entries
and fingerprints remain valid; both modes share the event-ID namespace and capture lock.

A failed write can leave a pending event. Retry the exact payload and event ID: the original
timestamp chooses the day and the journal marker prevents a second section. A changed payload
with the same event ID is rejected. This is explicit retry, not background recovery; the ledger
does not contain enough information to reconstruct a missing payload. Pause skips either mode.

## Verification — 2026-10-16

The first focused test failed on missing note ID before the implementation. The completed suite
passed 43 tests, with one native-symlink privilege skip on Windows. Ruff passed. Tests cover
note preservation, no searchable note, duplicate events, changed-payload/cross-mode conflicts,
scope/secret/schema rejection, pause, concurrent note/journal writes and Windows junction escape.
Injected journal-write and final-ledger-write failures both recover on an identical next-day retry
without moving the event or creating a second section. CLI tests use isolated temporary config.

Two independently started stdio MCP server processes saved then deduplicated a synthetic event;
status remained zero notes and zero pending events. This verifies the MCP protocol, not that a
previously running Codex server has loaded new code. That host can use the updated CLI meanwhile.
No personal vault data or raw tool responses are included in the repository.

The actual personal CLI also recorded this implementation milestone: the first call returned saved
and an identical retry returned duplicate. Local assertions confirmed one journal marker, unchanged
canonical-note count and unchanged unrelated pending-event count. The installed skill was updated
after verifying ownership, with skill/manifest backups and a matching new ownership hash.

This targeted feature task is not an unbiased ordinary-task capture-rate study. Such a study
still needs independent eligible tasks and observed completion outcomes, including skipped and
failed captures; none of the synthetic tests or explicit host probes establish lifecycle automation.
