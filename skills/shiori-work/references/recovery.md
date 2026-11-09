# Recover the work connection or an interrupted write

If MCP fails at startup, transport or discovery, check this installation's stable
`shiori.cmd run status`, `run doctor --catalog` and read-only retrieval. A validation error
means the server responded. Check the documented arguments. Use the configured work installation
only, with its existing launcher and config. If it also fails, report the actual
manifest/interpreter/configuration problem and continue the main task.

## Read-only fallbacks

Check the installed `shiori.cmd run --help` and command help. These commands are scoped to the
managed work installation.

| Need | Arguments after `shiori.cmd run` |
| --- | --- |
| Find an exact note or tags | `search --id note-id` or `search --tag tag-id` |
| Read literal Markdown | `read note-id --format text` |
| Inspect an issue or list task pages | `task read DEMO-1234` or `task list` |
| Resume a project or check journal tasks | `project-resume project-id` or `journal --view tasks --project project-id` |
| Search diary entries | `journal --project project-id --query "example"` |
| Search favorites | `favorites list "echo" --tag comando` |
| Inspect log state, actions or one event | `agent-log status`, `agent-log list` or `agent-log read event-id` |
| Inspect pending capture IDs | `pending` |

## Recover an uncertain write

A timeout leaves the outcome unknown. Keep the exact original candidate and event ID. Check
the corresponding record and pending state before an identical retry. A changed payload
requires a new event ID after you have reconciled the original. Pending capture lists carry
IDs and fingerprints. Recover the candidate from your retained JSON.

- **Checkpoint**. Check `memory_status.pending_checkpoint`. If it names the event, retry
  `record_checkpoint` with the original candidate. Its component writes belong to that operation.
  Use the checkpoint tool to complete them. A paused deployment needs an explicit resume.
- **Note or diary**. Inspect `list_pending_captures` or `run pending`. Retry a pending note
  first with its original payload. Use `capture --event-file ...` on the same work installation
  for an intentional CLI retry after checking the state.
- **Agent Log**. Look up the event by ID, then use its original payload with `record_agent_action`
  or `agent-log record --event-file ...`. Resume the log write only.

## Reviewed CLI capture

`run note --request-file request.json` searches and classifies a candidate plus its work
assessment. `--apply` writes the returned candidate. Inspect the diff and truncation.
For a separately reviewed update, use `--expect-revision` with the preview's `base_revision`
or `absent` for creation. Select note IDs by identity, using related text matches as context.

Supported versions accept UTF-8 JSON on stdin with `classify` or `note --request-file -` and
`capture --event-file -`. Preserve the exact submitted JSON privately for any retry. Check the
installed help for supported commands and report an update requirement when a capability is absent.
