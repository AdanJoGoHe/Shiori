# Explorer and themes acceptance — 2026-10-22

Refs #34, #45 and documentation review #23. This is acceptance of the local personal MVP,
not the full v1/M5 release gate, a hosted service or an accessibility certification.

## Reproduce locally

Use a development checkout with its Python environment, preinstalled Node, Playwright and
Edge/Chromium. No frontend dependency is added to the product. Run:

```powershell
$env:SB_TEST_NODE = '<absolute Node executable>'
$env:NODE_PATH = '<development node_modules containing Playwright>'
$env:SB_TEST_BROWSER = '<absolute Edge or Chromium executable>'
.\.venv\Scripts\python.exe scripts/check-explorer-workflow.py
```

Optional `SB_TEST_SCREENSHOTS` names an existing local directory for synthetic viewport captures.
Do not supply an owner viewer URL: the runner creates its own loopback server, browser profile,
vault and state under a checked temporary directory. It stops only its threads/server, closes
the browser, verifies original fixture bytes and removes its own fixture. Restart closes and
recreates the server on the same port with a new capability, reopening the saved browser profile.
No config/vault/ACL/host installation or running owner process is changed.

## Observed workflow

- 25 readable Markdown documents, two managed command notes and a journal. The largest readable
  document is 22,003 UTF-8 bytes; additional rejected inputs are invalid UTF-8 and 1,000,001 bytes.
  A configured empty collection and an out-of-root sentinel exercise absence and boundaries.
- Real listing/search responses: documentation pages of20 and5 rows; next/previous; empty source;
  malformed/oversized sources produce partial diagnostics and retain valid results.
- Knowledge query combines two tags, project, command type, verified status, agent and inclusive
  same-day bounds. Reader shows evidence, follows a known note link and returns with query,
  tags/type/date retained. Documentation code/table/internal link and unavailable external-root
  link are exercised separately. Navigation uses focus/Enter; the theme selector uses Home,
  arrows and Tab, with assertions on the actual applied theme.
- Script HTML is inert, remote Markdown images are not loaded, unsafe URLs are not activated.
  Browser requests in the assembled workflow were same-origin GET only; no upload/telemetry or
  external resource request occurred. Provider search is guarded against use: this explorer uses
  canonical files without an index. This does not certify every dependency's network behavior.
- Original docs, managed notes and ledger bytes remain identical; no annotations store is created.
  Source APIs reject writes in HTTP tests. The separately authorized annotation/category endpoints
  **do** support protected sidecar writes; “read-only” refers to source Markdown, not absence of
  every mutation endpoint. Their Origin/version/secret/recovery boundaries have separate tests.
- Companion `check-viewer-states.cjs`:54 combinations of six controlled response states,
  three themes and1440/820/390px, keyboard refresh/retry/open/back and stale-server warning.
  Controlled responses check presentation; real-file/API error classification is covered by
  `tests/test_viewer.py`. No page errors or page-wide horizontal overflow were observed.

One regression found during acceptance: source choices were derived only from readable rows.
Configured empty/unavailable roots disappeared, and a selected root hid the other choices.
Choices now use validated configured source IDs for the collection, without another scan or
initializing absent roots. The new regression test failed before the fix and passes afterward.

## Theme evidence

Claro, Oscuro and Café Latte share CSS variables. The default is always Claro, regardless of
the OS theme. Invalid or unavailable localStorage falls back to Claro; blocked storage still
allows a temporary theme switch and reading. The synchronous local theme script precedes CSS.
This ordering avoids a wrong-theme stylesheet load; no instrumented first-paint guarantee is made.

Nine actual theme/viewport combinations pass switching/reload and reading. A new server instance
on the same origin preserves Café Latte through the persistent browser profile. Queries reset;
only `second-brain-theme` is in localStorage. Browser origins/ports/profiles have separate preferences.

Computed foreground/background contrast, worst of the sampled elements:

| Sample | Claro | Oscuro | Café Latte |
|---|---:|---:|---:|
| Body/table text |13.98:1|12.68:1|12.03:1|
| Code text |12.76:1|14.60:1|10.10:1|
| Reader links |7.57:1|8.98:1|7.18:1|
| Tag text |5.09:1|6.02:1|5.14:1|
| Warning text |6.12:1|9.53:1|6.49:1|
| Focus outline against canvas |7.01:1|10.17:1|5.98:1|

Text samples exceed4.5:1; sampled focus exceeds3:1. This is not an audit of every pixel/state.
All six highlight colors and native selection have additional
[annotation workflow evidence](annotation-acceptance.md); the six-phase runner also passed
after this source-choice correction. Physical phone, IME and screen-reader certification remain
unclaimed; narrow layouts and touch emulation are distinguished from physical devices.

## Performance and environment

Windows, Python3.12.14, Edge155.0.4283.62, Basic Memory0.23.2, markdown-it-py4.2.0,
FastMCP4.0.0b1; package0.1.0a1. No new Linux or physical Codex MSIX installation was tested.
HTTP search samples over25 readable docs:102/96/96ms (median96ms).
Nine reader-open-to-two-animation-frame samples:6357/327/250/238/215/238/223/238/238ms.
The first sample was6.36s; median238ms. This includes keyboard action, local HTTP requests,
rendering and paint scheduling, not isolated renderer CPU time. These are local observations,
not an SLA, large-vault benchmark or a diagnosed performance regression.

Source validation:289 passed, one native Windows symlink-privilege skip; Ruff check/format and
CLI help pass. Separate junction coverage passes. A fresh wheel/constraints installation outside
the checkout passes `scripts/verify-release.py`, including8 fresh-stdio tools, actual isolated
provider search/probe, reversible install/upgrade/uninstall and paused backup recovery. Its provider
teardown emitted a SQLAlchemy/asyncio cancellation traceback; acceptance assertions and exit0
passed. No provider shutdown fix is claimed here.

Guide review: all three JSON examples parse;13 PowerShell blocks parse without executing install
or permissions changes. The guide's draft/classify/capture/duplicate/journal/context/pause/resume/
doctor flow passes against a disposable config. File links resolve. Recovery and unrelated-settings
preservation are exercised by the installed-wheel scenario, not an owner reinstall.

Initial helper iterations exposed assertion/timing mistakes (missing schema in a test config,
catalog `items` versus a nonexistent `total`, premature browser teardown and a Windows trial-click
stability timeout). Helpers now use the real contracts, reader busy state and explicit keyboard
focus. Final browser run completed without server tracebacks; no product networking fix is claimed.

Full v1/M5 acceptance in specification section15 remains open: Claude/Augment applications,
automatic hooks/capture-rate studies and release/update gates have not been demonstrated. #23's
documentation is current for the personal alpha, but its original M5 acceptance must stay open
until those dependencies are met. Graph/timeline is disabled and does not block this explorer MVP.
No Actions dispatch, release/tag publication or owner deployment change occurred.
