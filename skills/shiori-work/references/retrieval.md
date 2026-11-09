# Retrieve work context

- **Known issue code**. Read [Issues and checkpoints](tasks.md) and start with `get_work_context`
  when available. Use the issue code and request only the sections you need.
- **Technical topic**. Use `get_context` with a narrow query and exact project/tags when known.
  Follow note IDs with `read_memory` when excerpts are insufficient. Check verification, date,
  evidence and truncation. For an exact ID use the server's `search_memory(note_id=...)` when advertised.
- **Resume a project**. Use `resume_project(project=...)` for recorded active tasks, versions and
  the latest effective progress. Check `error_count`, `tasks_omitted` and `truncated`.
- **Diary and recaps**. Use `read_journal` with the requested project and dates. The default window
  is seven local days. Use inclusive YYYY-MM-DD dates for a window of up to 31 days. Use
  `query` for text lookup when advertised, follow `next_offset` and inspect errors and
  `content_truncated`. For recaps, cite dated records and separate results, checks and pending
  actions. Verify whether a historical blocker still applies.
- **Favorites**. Use `read_favorites` for a requested favorites search. Filters for project, tags,
  kind and target are exact. Follow `next_offset`, inspect errors and `catalog_truncated`, and
  use the authorized `content_id` for local reading. Web favorites are inert references. Favoriting
  expresses preference. CLI save/remove requires explicit user intent and reviewed data.

For unavailable tools, use the [same-profile CLI](recovery.md#read-only-fallbacks).
