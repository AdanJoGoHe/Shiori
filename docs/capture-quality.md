# Capture quality preview for agents

Refs #18. MCP `classify_memory(candidate, assessment)` and CLI
`classify --request-file '<request.json>'` make an explicit, read-only decision before capture.
No new model call, dependency, event reservation, ledger migration or host setting is introduced.
Direct capture remains compatible; this preview is not a mandatory privacy gate for old callers.

Search related personal notes before proposing an ID; use the same ID for a correction. Prepare
only curated, non-secret personal information. Do not send corporate/customer material, raw logs,
conversations or inferred personal preferences to this deployment, including to the classifier.
Privacy declarations are agent assertions: the classifier cannot recognize all sensitive prose
or independently validate a cited source/test. A regex secret check is an additional safeguard.

The request has exactly `candidate` and `assessment` fields. Candidate uses the existing capture
schema. Assessment requires all four fields, with no extras:

```json
{
  "candidate": {
    "scope": "personal", "id": "synthetic-example", "event_id": "example-event",
    "type": "lesson", "status": "verified", "source_agent": "codex",
    "title": "Synthetic lesson", "body": "A reusable observed lesson.",
    "evidence": "Describe the actual observed check here.",
    "summary": "Completed a meaningful check."
  },
  "assessment": {
    "material": "personal", "reusable": true, "meaningful": true,
    "evidence_kind": "observed"
  }
}
```

`material`: personal, corporate, customer or unknown. `reusable` and `meaningful` must be
booleans. `evidence_kind`: observed, source, user-confirmed or none. No numeric relevance score
or automatic inference is claimed. Evidence describes an actual check, authoritative source or
explicit confirmation; an agent proposing a fix is not verification. Failed approaches can be
reusable lessons when the failure and applicability are recorded. Preferences need explicit
user intent; the classifier does not infer it from prose.

| Priority | Condition | Decision |
|---|---|---|
| 1 | Non-personal scope; unsafe/oversized input; invalid assessment; material not explicitly personal | deny |
| 2 | Neither reusable nor meaningful | skip |
| 3 | Reusable verified note without declared evidence kind or nonempty evidence | Prepare as unverified; warn; continue validation |
| 4 | Not reusable, or explicitly journal-only | Prepare only the six journal fields; require an explicit summary |
| 5 | Invalid prepared capture fields | deny |
| 6 | Capture paused | skip |
| 7 | Existing event ID with a different prepared-payload fingerprint | deny |
| 8 | Identical committed event | skip |
| 9 | Journal candidate | journal-only |
| 10 | Exact canonical note ID exists | update |
| 11 | New exact note ID | save |

All supplied candidate fields are secret-scanned before filtering or skipping, including fields
that will not reach a journal. Sensitive input is rejected rather than silently redacted into
a misleading command/fact. Replace secrets upstream with meaningful placeholders and reassess.
Unknown secret formats and mislabeled corporate prose remain outside regex detection.

Save/update/journal-only results include `candidate` and `warnings`; deny/skip contain only a
fixed `decision` and `reason`, without echoing any text. Missing evidence never promotes a note
to verified; unverified/draft stays as supplied. The caller's dictionary is not modified.
Journal projection discards note/metadata fields only after scanning the entire input.

Review the result, then submit its **returned candidate** to `capture_memory` or CLI capture.
Keep that exact JSON and event ID until saved/duplicate. Never retry an older event with a
newly normalized/different payload. An identical pending event gets a `pending-event-retry`
warning. Preview does not guarantee a write will succeed: another capture, pause, pending-note
guard, unmanaged file or I/O failure can affect the later write, which revalidates everything.
Changing state between preview and capture does not grant authority to overwrite it.

The CLI returns JSON with exit code zero for classification outcomes including deny/skip;
invalid request envelopes or I/O errors exit nonzero. It accepts a request file up to 40 KB;
the core scans at most 30000 candidate characters using the existing bounds. Existing MCP
processes must reconnect for discovery; updated CLI works in a new process.

Synthetic tests cover reusable observed/source/confirmed notes, failed attempts, preferences,
missing evidence, draft preservation, exact updates, metadata preservation on later capture,
journal-only and trivial skip, corporate/customer/unknown denial, secret input in discarded
fields, malformed data, pause, duplicate/conflicting/pending events, no preview mutations and
fresh stdio MCP/CLI parity. No real-host semantic classification, independent evidence checking,
semantic duplicate detection, secret redaction, automatic capture or other-host acceptance is
claimed. These remain broader #18/#16 work; the issue stays open for acceptance.
