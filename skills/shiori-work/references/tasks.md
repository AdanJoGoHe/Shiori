# Issues, checkpoints and journal tasks

## Issue context and edits

Call `get_work_context(issue_key=...)` for the issue's current task page, explicitly linked
notes and recent diary progress. Request `task`, `notes` or `recent_progress` with `include`
as needed. The recent window is 31 local days. Treat a suggested next step as recorded history,
especially when progress predates the task edit. Inspect warnings and truncation.

Use `get_task_page` for full details and the current version. Use `list_task_pages` to browse
by exact project, status and tags. With `save_task_page`, send the exact issue code,
`expected_version`, partial `changes` and a unique `event_id`. Create with version 0 and a title.
A supplied list replaces that field. On conflict, reread and review the change before using
a new event ID. For an uncertain response, retain and retry the identical request.

## Record an issue checkpoint

Use `record_checkpoint(candidate=...)` for progress on an existing page. Include
`scope: "work"`, `issue_key`, its current `expected_version`, a unique `event_id`,
`source_agent`, `summary` and the relevant [progress lists](capture.md). Include `status`
only if its new state is known. The tool writes the diary advance and the task page's latest
summary and next step. Include reviewed `knowledge` only for a new reusable note and
`agent_action` only for a reviewed [Agent Log action](agent-log.md).

If interrupted, keep the whole original candidate and follow [Recovery](recovery.md).
For an older server without checkpoints, report the missing feature. Use a reviewed journal
capture if progress needs recording, with the task project and lowercase issue code as
`activity`. For an unassigned task, include the exact code in the journal title.

## Small tracked tasks in the Diary

Use journal tasks for work without an issue page. They require an explicit project and each
change includes `id`, `title`, `status` (open/blocked/done/discarded), `details` and
`version`. Create at 0. Read the current version before updating or reopening. Use
`read_journal(view="tasks", project=..., offset=...)` for all states and history.
Mark done only after observed completion. Resolve stale versions and pending writes before
another change. [CLI retrieval](recovery.md#read-only-fallbacks) is available for supported
versions.
