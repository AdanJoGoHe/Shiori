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

Journal-only candidates contain exactly scope=`work`, mode=`journal-only`, event_id, title,
source_agent=`augment-jetbrains` and summary. They create no canonical note.

Retain the exact candidate JSON until saved/duplicate. Identical event retries are deduplicated;
changed payloads require a new event ID. A pending-note result requires retrying its original JSON
first. `list_pending_captures` lists identifiers, not original bodies: never reconstruct a payload
from an excerpt. Report only returned outcomes; capture failure does not block the main task.
