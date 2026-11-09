# Capture knowledge and progress

Search before choosing a note ID. Reuse its exact ID for a topic update and use a new event ID
for a new change. Save reusable commands, decisions or lessons with evidence. For meaningful
progress alone, use journal-only mode. Use [a checkpoint](tasks.md#record-an-issue-checkpoint)
when the advance also belongs on an issue's task page.

1. Preview with `classify_memory(candidate, assessment)`. The work assessment has
   `material: "corporate"`, booleans `reusable` and `meaningful`, and `evidence_kind`
   from `observed`, `source`, `user-confirmed` or `none`. These fields express your review.
2. Check the returned decision, candidate and any update diff. Submit the reviewed candidate to
   `capture_memory` for save, update or journal-only. Keep the exact submitted JSON and event ID
   privately until saved or duplicate. For uncertain outcomes, follow [Recovery](recovery.md).
3. Report the returned outcome. Use the next meaningful checkpoint or handoff to capture progress.

For a note, use `scope: "work"`, stable `id`, unique `event_id`, `title`, `type`, `status`,
`source_agent` and `body`. Use `source_agent: "augment-jetbrains"` in Augment JetBrains and
the appropriate supported agent elsewhere. Verified notes require observed or sourced evidence.
Keep untested claims unverified. Optional metadata includes `project`, `tags`, `related`,
`source_refs` and `sensitivity`. Omitted metadata survives an update. Empty lists and a null
project clear those values. Sensitivity is descriptive.

For a journal-only capture, use `mode: "journal-only"`, `scope: "work"`, `event_id`, `title`,
`source_agent` and `summary`. Either mode can add a project and `progress` with
`completed`, `checks`, `decisions`, `blockers` and `next_steps`. Each list accepts at most
eight nonempty strings of 500 characters. Record actual outcomes and checks. Put plans and
unresolved work in next steps and blockers.

Use an explicit project for continuing activity, corrections and journal tasks. Reuse its
`activity` slug for the same work. Identical journal-only progress in the same activity and
day can be skipped. To correct an entry, give `supersedes` with up to eight committed IDs in
that project and a `change_reason`. The original remains in history. Reconcile task state
separately from corrections to journal text.
