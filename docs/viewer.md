# Local visual library

Local personal explorer under epic #27, with [assembled MVP acceptance](explorer-acceptance.md). It consumes the catalog from #29.
The implementation uses Python's local HTTP server, packaged HTML/CSS/JavaScript and the already
installed markdown-it-py, now declared directly in the lock. No frontend build step or CDN.

## Run and stop

`second-brain viewer` loads the existing personal config and prints a temporary local session URL.
Open it in a browser. Optional `--port 8765` chooses a port; default 0 uses an available one.
The bind address is fixed to 127.0.0.1. Stop a foreground launch with Ctrl+C. Restart generates
a new session URL. No service, scheduler or system startup entry is installed.

`python scripts/demo-viewer.py` starts the same viewer with three documents, two notes and a journal
in a new temporary deployment. All content is marked synthetic; Ctrl+C removes only that temporary
directory. Use the demo for screenshots, browser validation and reviews; keep real notes out of GitHub.

Documentation roots retain the [catalog configuration](catalog.md). Refresh sees file changes;
restart to load configuration changes. Uninstall the package/stop the process to remove the viewer;
vault/state and prior installation backups are preserved. Existing MCP processes are independent.

## Interaction

Collections distinguish documentation, canonical knowledge and dated journal progress. Full-text
search matches all requested words, ignoring case and diacritics. Results combine exact selected
tags, source, project, type, status, agent and inclusive updated-date bounds. Empty/unknown metadata
can be selected. Relevance, updated time and title ordering are deterministic; pages contain 20 rows.
Filter choices come from authorized content in the current collection/source. Query, filter and
selection state stays in page memory, not URL parameters, local storage or analytics; reload resets it.
The Tema selector separately offers Claro (default), Oscuro and Café Latte. Only the theme name
is saved in browser localStorage; unavailable/invalid storage falls back to Claro. A local script
runs before CSS to avoid a wrong-theme first paint; native controls use the matching color-scheme.
Preferences belong to the browser origin: using the same viewer port preserves them across server
restarts; a different port/browser has a separate preference. Text, code, table, filter, link and
warning palettes and all six reader highlight colors have real-browser contrast evidence; see
[explorer/theme acceptance](explorer-acceptance.md) and [annotation acceptance](annotation-acceptance.md).
The default is always Claro, independent of the operating-system theme; no automatic system mode.

Open a result in the adjacent reader on desktop. At widths up to 1000px the reader replaces the list;
Back preserves its search/filter state. Reader tags can filter the list; internal allowlisted links
and known [[note-id]] references navigate the reader. It shows provenance, dates, verification
status, evidence text, related notes and a generated heading index. Missing/out-of-root links show
a message. Existing Markdown fragment links currently return to the reader start; the generated
index links to exact headings. Graphs, backlinks, match highlighting and saved views remain future work.

## Boundary

The session URL includes a random capability: treat it as private while the process runs. Host and
Origin checks reject foreign requests/DNS rebinding attempts; no CORS permissions are granted.
Source-document routes reject mutation methods. The separate annotation API below permits only
validated sidecar mutations with an explicit matching Origin and JSON body. Responses disable caching, embedding, external resources
and referrer forwarding; access logs omit paths, queries and content. This is a local development
viewer, not a hosted multi-user service or a sandbox against other programs acting as the owner.

Content IDs must resolve through a current bounded catalog, then path checks run again. There is
no arbitrary-file route. Approving a documentation root authorizes viewing its bodies, not merely
metadata: keep roots narrow and curated. Documentation is not automatically classified as secret-free.
Raw Markdown HTML is escaped, image parsing is disabled, unsafe URLs are not activated, and scripts
cannot run. External links require an explicit click and open without an opener/referrer.
Journal transaction markers are hidden and progress is not relabeled as verified knowledge.

The catalog's 2,000-entry/1 MB file budgets remain. Filter/search requests scan current content;
there is no new persistent index. Error/truncation states are visible. Files may change between
listing/reading and offset pages are not snapshots. Canonical note search/MCP behavior is unchanged.

## Observed verification — 2026-10-16

- 86 tests passed, one native Windows symlink privilege skip; Ruff lint/format and locked resolution passed.
- HTTP tests cover loopback bind, session route, Host/Origin/cross-site rejection, no write routes,
  scoped content IDs, safe rendering, asset serving, response headers and unchanged source files.
- Search/filter tests cover diacritics, combined facets, date validation, deterministic paging,
  hidden event markers, known note links, forbidden paths and hostile HTML/images/JavaScript URLs.
- Actual browser with disposable synthetic content: collection switch, combined tag/project/status,
  accent-insensitive query, empty results, reader/evidence, table, internal document navigation,
  date bounds, keyboard focus and return with query retained passed. At 549×800 no horizontal overflow
  was observed; the temporary viewport override was reset. No browser console errors observed.
- Wheel built successfully and contains all three offline assets.
- Local synthetic benchmark: 100 small Markdown documents, three full-text requests, 505/173/171 ms
  (median 173 ms). This is an observed fixture baseline, not a performance guarantee or load test.

This does not establish graph/timeline completion, a comprehensive accessibility audit or a production
hosting security review. Issues remain open for review and their broader acceptance scope.

## Annotation storage increment — #39

The original #39 increment supplied annotation storage and its HTTP contract. Subsequent category,
anchor and reader control increments are documented below.

`api/content?id=<catalog-id>` now also returns `text` and a SHA-256 `revision` of the source Markdown.
`text` is the safe rendered reader body's `textContent`, including renderer whitespace, with metadata
and the duplicated title omitted. Selection `start`/`end` are zero-based, end-exclusive **Unicode code
point** offsets in that string; JavaScript must convert UTF-16 offsets for non-BMP characters.
Prose, inline code and code-block text use the same contract. Offsets are specific to this renderer;
persisted exact quote, 120-code-point prefix/suffix and source revision support later anchor repair.
Existing marks can become stale after edits; see the resolution contract below.

All routes are relative to the private session URL:

| Method | Route | Body / result |
|---|---|---|
| GET | `api/annotations?document_id=<catalog-id>` | Saved `items` plus display-only `anchor` resolution; retained marks remain available if their source disappears |
| POST | `api/annotations` | Create with `document_id`, `revision`, `start`, `end`, `quote`, `color`, `tags` |
| PATCH | `api/annotations?id=<annotation-id>` | Same fields plus the current annotation `version` |
| DELETE | `api/annotations?id=<annotation-id>` | Current `version` only; returns a session-only undo token, including for stale/orphaned marks |
| POST | `api/annotations/undo` | `token` from the latest successful HTTP deletion in this viewer session |

Writes require an exact matching Origin and Host, `Content-Type: application/json`, a single bounded
Content-Length (up to 24 KB), and the session URL. Cross-site/same-site mutation requests, transfer
encoding and arbitrary path parameters are rejected. Browser CORS permissions remain absent. Wrong
source revisions/selections or concurrent edits return 409; malformed or unavailable data returns 400.
The local owner/session capability authorizes all annotations; this is not a multi-user permission model.

Annotation IDs are random and stable; versions increment on edits. Quotes are limited to 4,000 code
points, with at most 20 distinct category IDs (lowercase slugs). Colors currently accept `yellow`,
`green`, `blue`, `pink`, `orange`, `violet`; the category manager previews these colors with readable labels.
The existing secret-pattern validator also applies to saved quote/context. Tags here are fragment
category IDs, distinct from note metadata. There is no IP/command auto-detection.

Data lives only in the configured state directory: `annotations.json`, `annotations.previous.json`
(one prior complete snapshot) and `annotations.lock`. Sources and the capture ledger/journal are not
modified. File locking and version checks protect simultaneous edits; validated atomic replacement
preserves the prior store on a failed commit. A malformed store blocks writes instead of resetting data.
Limits: 1,000 annotations and an 8 MB UTF-8 store, with no persistent search index added.

For a deliberate backup, run `second-brain annotations-export --output <new-backup.json>`. The command
refuses to overwrite an existing export. Keep exports private: they contain selected text and context.
To recover, stop the viewer, copy the export or `annotations.previous.json` to a separate safe file,
then run `second-brain annotations-restore --input <safe-backup.json>`. Restore replaces the complete
annotation collection after schema validation and retains the current valid collection as the prior
snapshot. It preserves the last good prior snapshot if the current store is corrupt. Restart the viewer;
restored IDs may reference changed/unavailable documents and must not be assumed to resolve automatically.
Schema 3 exports restore annotations, titles/descriptions and category configuration together, never source Markdown. Legacy schema 1/2 imports remain supported.

### Fragment categories — #41

Open **Etiquetas de fragmentos** below the document filters. It has an independent list and form
for Comando, Información importante, Dirección IP, URL and Ruta plus owner-created categories.
Create, edit name/color, archive and restore; each row also shows its saved annotation usage count.
Names and color names accompany the color swatch, with keyboard focus and wrapping on narrow screens.
The manager's draft is not stored in the browser. On a conflict it stays in the form; cancel/reopen
the category to review the current version before retrying.

Names are whitespace-collapsed/NFKC-normalized and limited to 100 code points. Duplicate comparisons
ignore case and combining accents, including archived categories. IDs stay stable on rename/recolor.
Up to 100 categories, **including archived ones**, fit in the existing 8 MB bounded store. Reuse or
restore an archived category instead of creating a duplicate. Seed defaults are created in memory
only; reading/opening the panel does not write state.

Archive is reversible removal from future choices. Existing references keep their names and colors;
edits may retain an already attached archived tag, but new references to it are rejected. Multiple
active category IDs may tag one annotation. The annotation's saved `color` is always an explicit
override, independent of category colors; category order has no precedence and recoloring a category
never recolors existing annotations. Reader selection/tagging controls are described below.

| Method | Route | Body / result |
|---|---|---|
| GET | `api/categories` | All categories with stable ID, label, color, archived flag, version and usage count |
| POST | `api/categories` | Create with `label`, `color`; returns server-generated stable ID |
| PATCH | `api/categories?id=<category-id>` | Full `label`, `color`, `archived`, current `version`; rename/recolor/archive/restore |

These writes use the same session, Host/Origin, bounded JSON, file lock, version conflict and atomic
backup protections as annotation writes. DELETE is rejected; archiving preserves references. New
annotation tags must resolve to active categories. Read-only source/metadata and capture remain unchanged.

Schema 3 stores `items` (including optional title/description values) and `categories` in
`annotations.json`. Schema 1 files adopt seed/legacy categories; schema 1/2 items adopt empty
`title`/`description`. Conversion happens only in memory on read. The first successful sidecar
mutation, including a category edit or deletion, writes schema 3 and backs up the exact old bytes.
Preserve an independent private compatible export/file **before any mutation after upgrading**
if a downgrade is needed. Builds supporting only schema 1/2 cannot read schema 3; reinstalling an
older executable does not reverse data formats. Importing an old export with this new version
also writes schema 3: use a matching older tool/compatible deployment for a deliberate downgrade.
The one prior snapshot rotates on later writes.
Current export/restore includes categories, names, archived state and versions in the same transaction.

Observed category checks: synthetic round-trip, old-schema adoption, retained references, duplicate
names, archive/restore, stale and concurrent edits, limits and protected HTTP writes. Browser checks
cover create/edit/archive/restore, reload, inert HTML-like names, keyboard edit/cancel and375px layout.
Reader highlight and native selection acceptance is now recorded in
[annotation acceptance](annotation-acceptance.md); older component-only measurements below are historical.

### Anchor resolution increment — #42

Each listed annotation adds `anchor`: `status` (`resolved`/`unresolved`), `reason`,
`start`, `end` and current `revision`. Saved quote, context, offsets, revision,
version, ID, color and tags stay unchanged; listing never commits a repair.
The source is still read exclusively through the trusted catalog. Unavailable
sources expose retained sidecar text only, with no filesystem fallback or private error details.

An unchanged revision and matching selection resolves as `current`. After edits,
the exact quote must have exactly one match with the complete saved prefix and
suffix. A context shorter than 120 code points also requires the original document
boundary. Successful matches are `reattached`, including formatting-only source
changes. Duplicate matching contexts are `ambiguous`; offsets never break a tie.
Missing quote, changed context and unavailable source report `missing`,
`context-changed` and `unavailable`. Unresolved offsets are null.

This deliberately prefers manual repair when nearby text or document boundaries
change. There is no fuzzy matching or semantic identity guarantee for copied text.
Manual relink uses the existing PATCH with a fresh reader revision/selection and
current annotation version, preserving its ID. DELETE still removes missing-source
marks using their current version. Controls to show these states, relink and delete
in the reader are implemented in #40 and global search integration in #43. The assembled reader,
resolver and recovery acceptance is recorded in [workflow acceptance](annotation-acceptance.md).

### Named fragments — #73

Optional **Título breve** (up to120 Unicode code points) and **Para qué sirve** (up to1,000)
explain a marked command/IP/path/learning in plain text. Fill them on creation or use
**Editar detalles** on a saved mark, including unresolved or missing-source marks. Details-only
edits preserve exact quote/context, offsets, source revision, color, tags, ID and creation date;
version/updated time advance. They never repair an anchor or read an unavailable source.
Metadata is subject to the same secret-pattern checks; neither field is stored in localStorage.

Fragment search requires every query term across quote, category names, title and description,
ignoring case/diacritics. It is keyword search, not semantic inference. Document search remains
unchanged, and **Copiar fragmento** still copies only the literal quote. Titles/descriptions are
inert text in reader/results, survive undo/restart/export/restore, and may be explicitly cleared.

The protected PATCH route also accepts exactly `{version, title, description}` for details-only
updates. Full create/update accepts these two optional fields; omitted fields default to empty on
creation and retain the current values on update for older callers. Explicit empty strings clear
values. A stale version fails with409; invalid/oversized/secret fields fail without replacing the
store. Source-based selection updates keep their existing fresh-revision checks.

### Selecting and managing reader marks — #40

Select text **inside the reader body**, then choose **Marcar selección**. A preview shows the exact
quote and context before **Guardar marca** commits its color and optional multiple category IDs.
Code, inline code, multiline prose and headings use the same rendered-text contract. Metadata and
the duplicated document title are outside the selectable body. Cross-boundary selections and split
Unicode characters are rejected; the frontend converts DOM UTF-16 positions to Unicode code points.

For keyboard or touch use **Texto exacto para marcar**: type/paste the literal reader text and choose
**Preparar siguiente coincidencia**. Repeating cycles through occurrences with position and context
for explicit confirmation. It does not pick a repeated quote's identity automatically. Text must have
1–4,000 nonempty code points; whitespace is preserved, including code newlines. No drafts, quotes,
undo tokens or annotations are persisted in browser storage.

Saved ranges render without changing reader text, links or code structure. Overlaps retain every
annotation; the latest creation time determines visible color, with storage order breaking timestamp
ties. Every mark remains editable in **Marcas guardadas**, including an obscured overlap. Non-link
marks also have keyboard-focusable edit actions; links retain navigation. Color names, category
labels and state text accompany the color. Six colors use a shared dark foreground with contrast
at least9.93:1; native reader text selection uses white on#173f6f in all themes.

**Ver / editar** prepares the current resolved range and existing category IDs. Save is versioned;
on conflict keep/copy the draft, then explicitly reload to review current source/state. Navigation
while saving still targets the originally selected document and never repaints a different one.
**Volver a enlazar** retains ID/color/tags while the owner chooses a new range. Cancel repair to start
a separate mark. Missing/ambiguous/context-changed states retain quote and category labels. If a
document disappears while open, **Recargar marcas** keeps its saved marks available for delete/undo;
find such orphaned marks after leaving the document using global fragment search (#43).

**Eliminar marca** is immediate and offers **Deshacer eliminación**. The server retains one deleted
record with an opaque token in memory, not in the export or browser storage. Undo restores its ID,
created date, quote, anchor, color and even archived category references, increments the version and
then consumes the token. It does not guess a new anchor or require a vanished source. A subsequent
successful HTTP delete anywhere in that server replaces the ticket; concurrent edits/restores and
store limits still fail safely. Restart expires server undo; browser reload, explicit reload and
document navigation discard the client ticket. Keep normal export/backups for longer-lived recovery.

Observed:130 tests pass with one native Windows symlink privilege skip. Browser checks used synthetic
data for mouse selection; keyboard literal selection; Unicode/multiline and inline code; overlaps
and tied timestamps; edit/delete/undo; repeated occurrences; rejected whole-page selection; reload;
linked navigation; modified/missing sources and manual repair;375px and all themes. Source bytes and
reader text were checked separately. Node checks exercise offset boundaries and overlap segmentation.
See the later [assembled workflow acceptance](annotation-acceptance.md). Physical phone/IME
and comprehensive assistive-technology certification remain unverified. One earlier
Windows managed-restart test returned `Path escapes root`; isolated rerun and the final full suite
passed. This observation is not a diagnosed fix to lifecycle/path resolution.

Observed storage verification: 102 tests passed and one Windows native symlink privilege test skipped.
New tests exercise restart/round-trip, CRUD/version conflicts, simultaneous edits, Unicode/code-block
offsets, unchanged source bytes, malformed selections/paths, protected HTTP writes, interrupted commit,
corrupt-store recovery and CLI export/restore without overwriting exports. This is backend verification;
real-browser selection/highlighting and a comprehensive accessibility audit remain pending.
An actual browser's reader-body text matched the new server text contract byte-for-byte (SHA-256)
for the synthetic installation guide, including prose, code, a table and an internal link.


### Global marked-fragment retrieval — #43

Choose **Fragmentos marcados**, then Comando, Dirección IP, Ruta or a custom category. Each row
is one saved annotation, with its verbatim multiline quote, up to 80 code points of context on
each side, labels/color, document identity and annotation update date. Copy sends only the quote
to the native clipboard (Windows may use CRLF); it never executes text. Opening selects the
exact range across DOM nodes/overlapping highlights; Back retains filters/page/list scroll/focus
within the current page. Reload does not persist quotes or filters in browser storage.

`GET api/items?view=fragments&category=comando` uses the existing protected route. Repeated
`category` IDs are AND, `__none__` selects untagged marks, `color` selects the annotation color.
All normalized search terms must match the quote/category labels, never just document body/tags.
Existing document metadata/kind/source/date filters combine with AND; dates and updated ordering
remain document dates, distinct from the displayed annotation date. Stable document+annotation
IDs break sorting ties; pages contain at most 20 marks. The 1,000-mark/8MB sidecar bounds remain.

Anchor resolution is display-only. Missing/ambiguous/context-changed quotes retain their saved
context and a repair state. For a document absent from the catalog, only retained sidecar text
is searched; metadata and document date are unknown and no alternate path is read. These rows
are limited to still-configured documentation sources or the personal note/journal scope and are
not appended when the catalog scan is truncated. Removing a documentation source excludes its
marks from this view. The current catalog health/error/scan-limit warning still applies; see
[catalog diagnostics](catalog-diagnostics.md).
A race between source loading and annotation resolution cannot navigate using a different revision.

Synthetic validation: category-only results, exact Unicode/multiline quotes, context, combined
facets, empty/untagged/multiple marks, stable pagination, archived categories, absent documents,
revoked sources, catalog limits and unchanged source/ledger/sidecar bytes. Browser checks cover
copy, keyboard category activation, exact navigation/Back, 375/768/1440px and all three themes.
These checks do not establish a Windows/MSIX path fix (#63–#65) or physical-phone acceptance.
