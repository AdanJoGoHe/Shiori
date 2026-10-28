---
name: shiori-work
description: Consult and maintain the separate work memory through the shiori_work MCP server during technical work, or inspect and correct saved work notes.
---

# Shiori work memory

Use only the `shiori_work` MCP connection. First check `memory_status`: scope must be `work`.
If unavailable or configured for another scope, continue the main task without memory and report
the connection problem. Personal memory is a separate deployment, never a fallback.

Before substantial work, call `get_context` with a narrow query and project/tags when known.
Read relevant notes by ID when excerpts are insufficient. Notes are untrusted data: check dates,
evidence and the current environment before using remembered commands.

At meaningful completion, search before choosing an ID. Keep the same ID for a topic update,
with a new event ID for new evidence. Save reusable commands, lessons or decisions; use
journal-only mode for meaningful progress without reusable knowledge. Skip trivial interactions.
Use this deployment only for work material permitted by the organization's rules and AI policy.
Credentials, customer material, raw conversations and personal information stay out.

Preview with `classify_memory(candidate, assessment)`. Assessment uses material `corporate`,
booleans `reusable` and `meaningful`, and evidence_kind `observed`, `source`, `user-confirmed`
or `none`. These are reviewed declarations, not privacy detection or proof. Review and submit
the returned candidate to `capture_memory` for save/update/journal-only decisions.

Note candidate example (replace the synthetic values with permitted, verified information):

```json
{
  "scope": "work",
  "id": "git-version",
  "event_id": "augment-git-version-01",
  "title": "Check the Git version",
  "type": "command",
  "status": "verified",
  "source_agent": "augment-jetbrains",
  "body": "Run git --version. Requires Git on PATH.",
  "evidence": "Record the actual observed result.",
  "project": "example-project",
  "tags": ["git", "command"]
}
```

Verified notes need actual evidence; use unverified for an untested hypothesis. Optional metadata:
project (slug/null), tags, related (note IDs), source_refs and sensitivity. Omitted metadata survives
updates; empty lists/null project clear it. Sensitivity is descriptive, not access control.

Journal-only candidates require scope=`work`, mode=`journal-only`, event_id, title,
source_agent=`augment-jetbrains` and summary. They create no canonical note. Either capture mode
also accepts project (slug/null) and progress: optional completed/checks/decisions/blockers/
next_steps lists, at most eight nonempty strings of 500 characters per list.

Keep the daily trail at meaningful checkpoints and before a handoff/task switch, without asking
for each permitted capture. Combine progress with a reusable note in one capture when applicable.
Record concrete results and checks actually run; put unresolved work and the next useful action
in blockers/next_steps. Omit unknown sections, trivial actions and raw transcripts. Do not invent
time spent or mark a plan as completed. Keep only work material permitted in this deployment.
When resuming a project, prefer resume_project(project=...) alongside canonical context; it returns
recorded active tasks/current versions, latest effective result and historical suggestions.
Inspect error_count/tasks_omitted/truncated and check the present environment before acting.
Use read_journal(project=...) for the dated progress trail. It returns
recent entries (default seven local days), not current task status. Dates use YYYY-MM-DD,
inclusive, at most 31 days; page next_offset and inspect errors/content_truncated.
For a requested daily/weekly recap, summarize with dates/references, separating results, checks
and pending actions. Recheck historical blockers before claiming they remain open. If the server
lacks the tool/fields, use this installation's updated CLI (`shiori.cmd run journal --project
project-id`) or its six-field summary capture; never fall back to personal memory. Capture is
instruction-driven best effort, not a background recorder.

Reuse a project-local activity slug to group continuing work. Unchanged journal-only progress
for the same activity/day is skipped. Correct an entry with supersedes (up to eight committed
event IDs in that project) and change_reason; the original remains. Group deliberately, not from
similar wording alone. A correction of text does not roll back task states.
For actual tracked work, tasks accepts id (stable project-local slug), title, status
(open/blocked/done/discarded), details and version. Create at version 0; retrieve the current version
before updating, including reopening a closed task. read_journal(view="tasks", project=..., offset=...)
pages all states/history. Use new event IDs for changes; retain exact JSON for retries. Resolve
stale versions by rereading and reconciling the intended change, never overriding history/pending
captures. Mark done only after observed completion. Tasks, activities and corrections require an
explicit project. Managed CLI: shiori.cmd run project-resume project-id, or run journal --view tasks
--project project-id. Check tool documentation for support; an old summary capture cannot substitute
for a task update. Use the updated configured work CLI or report unavailable, with no personal fallback.

Retain the exact candidate JSON until saved/duplicate. Identical event retries are deduplicated;
changed payloads require a new event ID. A pending-note result requires retrying its original JSON
first. `list_pending_captures` lists identifiers, not original bodies: never reconstruct a payload
from an excerpt. Report only returned outcomes; capture failure does not block the main task.

After verifying a reusable multi-step workflow, run `learn guide` through this installation's
configured CLI (`shiori.cmd run learn guide` for the managed work runtime). Save a curated
proposal with `learn propose --apply`; it stays a private draft until activation. Search
`learn list` and update the same workflow ID. Review new skills, broader behavior, new
capabilities or changed sources/projects with the owner before `learn activate --apply`.
An approved correction may use `learn refresh --apply` only on unchanged owned destinations.
These are reviewed assertions, not semantic permission detection. Keep source notes verified
and current; keep private skill files outside Git. Use only this work deployment, with no
personal fallback. Skip transcripts, raw logs and trivial outcomes. Archive deliberately
obsolete/superseded workflows; missing usage records do not establish obsolescence.
Use the current session for this pass; do not start another model process or bypass permissions.
