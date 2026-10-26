# Named fragment extension — 2026-10-22

Issue #73 adds optional title/description to marks and global fragment search. The same six-phase
synthetic browser runner now creates/edits names by keyboard, renders HTML-like descriptions as
inert text, finds commands by words found only in their title/description, and copies exact quote
only. It checks title/description after real process restart and formatting reattachment, keeps
them during explicit relink, edits orphan details without moving the anchor, and preserves them
through delete/undo and export/restore. The edit form wraps at1440/820/390px in all three themes;
local synthetic screenshots were inspected. Touch remains browser emulation, not a physical phone.

Source tests:297 passed, one native Windows symlink privilege skip; Ruff/format/CLI help pass.
Regression coverage includes version conflicts, oversized/invalid/secret metadata, old callers
omitting optional fields, keyword AND/diacritic behavior, protected HTTP orphan edits, schema1/2
read-only adoption, exact pre-migration snapshot and named-fragment backup/paused restore.
A new installed-wheel scenario also searches title/description over real HTTP.

Schema3 is written on the first successful sidecar mutation after upgrade; reads of old schema1/2
normalize only in memory. Original sources and capture ledger stay unchanged. Keep an independent
private old-format copy before writing if downgrade is needed; older executables cannot read3,
and the rotating prior snapshot is not a permanent downgrade backup. No owner migration/restart,
Actions dispatch or release publication in this extension. The original workflow evidence follows.

# Text annotation workflow acceptance — 2026-10-21

Scope: local personal annotations, reader controls #40, anchor resolution #42 and assembled
acceptance #44, completing the #38 child workflow. Source Markdown remains read-only to annotation
operations. Corporate deployment, external synchronization and automatic extraction remain excluded.

## Reproducible synthetic browser test

Requires the existing development Python environment, Node, optional developer Playwright and
an installed Chromium/Edge browser. These are test tools, not new product dependencies. The helper
does not install packages, read a personal config or connect to an already running owner viewer.

```powershell
# Optional if Node/browser are not discoverable through the developer environment:
$env:SB_TEST_NODE = $NodeExecutable
$env:SB_TEST_BROWSER = $BrowserExecutable
# NODE_PATH may point at an existing development installation containing Playwright.
.\.venv\Scripts\python.exe scripts/check-annotation-workflow.py
```

The Python runner creates a temporary vault/state/documentation fixture, spawns its own server
**process**, passes the synthetic capability URL to Node through stdin and stops only its own
processes. It persists no session URL. On completion it removes the temporary fixture. No screenshot
or personal payload is exported. The Node helper is intended only for this runner; it checks the
synthetic document ID, title and marker before testing writes.

| Phase | Executed behavior |
|---|---|
| Create | Native pointer prose selection; exact-text keyboard alternative for multiline code/Unicode, IP and repeated text; multiple categories, overlap, inert annotation/category markup, cross-boundary rejection |
| Manage/retrieve | Keyboard activation of a highlight edits color/tags; delete/undo with same ID and focus; category rename/recolor keeps explicit mark color; reload; combined categories/color/query/source/project; native clipboard contains only the quote; exact navigation through overlaps; Back preserves query/color/project |
| Restart | Stop/start a fresh server process over the same temporary store; mark IDs survive and session undo does not |
| Reattach | Change Markdown formatting; exact rendered quote/context resolves with the same IDs; no annotation-sidecar write occurs during checking |
| Ambiguous | Duplicate the source context; no guessed offsets; reader/search show ambiguity; manual repair to a unique new phrase preserves ID, tags and color |
| Orphan | Remove the document; retained quote/context remain searchable; fresh selection/relink is disabled; explicit delete/undo still works |
| Touch | Chromium touch emulation at390px: exact-text path/code/link marking, all six highlight colors, missing-text explanation, taps, fragment navigation and intact local links |
| Recovery | Export categories/annotations and restore to a separate synthetic store; exact round trip |

Each phase asserts that annotation operations preserve the current documentation bytes and the
original vault/ledger/note bytes. Source changes/removal are deliberate fixture operations between
phases, never annotation writes. Restart/reattach also preserve sidecar bytes. The browser checks
inert script/HTML, reports no JS page errors and exercises actual HTTP APIs rather than mocked
catalog responses. Desktop keyboard checks use a1000px viewport with the reader Back control.

All six rendered highlight colors were checked in Claro/Oscuro/Café Latte: minimum computed
text contrast **9.93:1** in each theme. Selected text uses the reader's explicit foreground/background;
category and selected-filter contrast is recorded in the [category and storage tests](../tests/test_categories.py).
Meaning is also shown by labels, saved quotes, state text, buttons and keyboard focus.

## Protected routes and failure recovery

Run the existing backend/DOM regressions alongside the real-browser workflow:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_annotations.py tests/test_categories.py tests/test_anchors.py tests/test_annotation_undo.py tests/test_fragment_search.py tests/test_reader_marks.py -q
.\.venv\Scripts\python.exe scripts/check-local.py
```

These cover capability/Host/Origin/content-type/fetch-site rejection, traversal/unknown paths,
optimistic version conflicts, concurrent edits, invalid imports, interrupted writes and previous
copy recovery. Resolver tests also cover inserted paragraphs, duplicates with distinct contexts,
Unicode boundaries and missing/changed context. Four Node DOM checks cover offset conversion,
overlap segmentation, stale refusal and exact ranges across nodes. Browser acceptance complements
these failure tests; it does not inject a failing filesystem into the owner deployment.

## Usage, storage and recovery

- Select text inside the reader or use **Texto exacto para marcar**, then choose color/categories.
  Overlapping marks remain separate; the most recently created mark determines overlapping color.
- Categories keep stable IDs. Renaming/recoloring a category does not recolor existing marks.
  Multiple categories filter with AND. Document tags and fragment categories remain distinct.
- **Fragmentos marcados** returns quote/context; **Copiar fragmento** excludes context and never
  executes text. Windows clipboard newlines may be CRLF. **Abrir ubicación** selects the exact quote.
- Ambiguous, missing and changed-context marks need deliberate review/relink, not an approximate
  position. A source absent from the catalog exposes retained sidecar text only. Restore that source
  from its own backup before trying to select text there again.
- Store: `annotations.json` under the selected deployment state directory, with
  `annotations.previous.json` for recoverable previous data. Export/restore are explicit local CLI
  operations; see [storage contract](viewer.md), [user guide](guia-de-usuario.md) and
  [backup boundaries](backup-restore.md). Do not replace the canonical ledger to repair a mark.
- Undo covers the latest deletion in the current document/session. It expires on document change,
  reload/restart or another deletion. It is not a backup. Reader offsets belong to this rendered-text
  contract; there is no fuzzy/semantic identity guarantee.

## Evidence boundary

Full local checks: **288 passed, 1 native Windows symlink privilege skip**, Ruff/format/CLI help
pass. Focused annotation/category/anchor/undo/fragment/DOM suite: **49 passed**. All six browser
phases and exact export/restore pass. One initial full run encountered `WinError10053` during an
existing negative HTTP-header/undo test; the isolated test, focused suite and final full run pass.
No guards/timeouts were weakened and no product networking fix is inferred from that transient.

Observed on Windows with headless Edge, actual pointer/keyboard/native clipboard, fresh Python
server process and synthetic files only. Narrow touch is **browser emulation**, not a physical
phone, long-press handle/IME study or screen-reader certification. Reduced motion makes automation
deterministic; this is not a comprehensive accessibility/security audit. No Linux run, physical
Codex MSIX test, owner runtime restart, release publication or Actions dispatch is claimed.
