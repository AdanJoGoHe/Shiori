# Compatibility

## Current status — 2026-10-30

Published release: [alpha.5](https://github.com/AdanJoGoHe/Shiori/releases/tag/v0.1.0-alpha.5).
Its dated acceptance is recorded below. The agent CLI changes in
[PR #18](https://github.com/AdanJoGoHe/Shiori/pull/18), commit `346a0db`, are later source:
551 local tests passed, one native Windows symlink-privilege skip; 34 agent-CLI tests passed
against the installed wheel. Personal/work verifiers passed with ten MCP tools and synthetic
data, including the real managed CMD launcher. This does not establish real Augment acceptance
or make those changes available through the published alpha.5 package.

The Windows local work profile is implemented. Actual JetBrains/plugin acceptance remains
[issue #2](https://github.com/AdanJoGoHe/Shiori/issues/2), with a
[manual checklist](augment-trabajo.md#lista-de-aceptacion-con-datos-ficticios).
No Linux run, actual two-device remote setup or active personal-deployment upgrade is claimed.

## Historical personal-alpha baseline — 2026-10-24

Personal-alpha evidence recorded on 2026-10-24. These observations do not automatically validate later source changes.

| Capability | Observed result and limit |
|---|---|
| Shiori identity | Viewer/MCP display names and packaged skill updated; installed `shiori` and legacy `second-brain` launchers select the same synthetic deployment. Package, MCP IDs, config/data and theme-storage key retained |
| Windows/Python | Python 3.12.14;337 source tests passed, one native symlink privilege skip; real junction checks pass |
| Memory export/import |17 synthetic transfer tests;31 transfer/recovery tests pass in a fresh installed wheel. Additive notes only, conflicts retained, original dates/bytes, pause/pending/concurrent/retry and complete backup after import checked |
| Authenticated HTTP MCP |23 synthetic tests pass from source and installed wheel, including real TCP/CLI and a verified local TLS proxy; actual VPN/certificates and two-device Codex remain untested |
| Browser | Edge155.0.4283.62; explorer/theme workflow and54 state/theme/viewport cases pass at1440/820/390px |
| Themes | Claro/Oscuro/Café Latte; reload and same-origin server restart retain preference; blocked/invalid storage works; OS theme is not followed |
| Annotations | Real-browser selection/repair/restart/recovery; six colors in all themes; touch emulation, not physical phone/IME certification |
| Packaged installation | Fresh wheel0.1.0a1 with locked constraints; actual isolated provider search/probe and8 stdio tools pass |
| Recovery/integration | Synthetic paused restore; owned upgrade/uninstall preserve unrelated settings; not two published-release upgrades |
| Codex application | Personal context retrieval and capture/read-after-write observed in a real host session. Fresh stdio is not a fresh Codex UI/session or automatic-capture proof |
| Linux | Historical hosted results only; no Linux execution in this batch. Routine checks are local under the Actions policy |
| Codex MSIX | Redirected-root simulations and native Windows filesystem checks; physical packaged-host acceptance unclaimed |
| Claude/Augment | Actual applications untested; no full cross-host claim |
| Work | Separate local profile and paired-store guard implemented; synthetic fixtures only. See [work setup](augment-trabajo.md). Actual employer device/plugin acceptance remains open |
| Hooks/automatic capture | Not installed; instruction-driven retrieval/capture remains best effort |
| Stable release | Full v1/M5 gates and published-release upgrade/rollback remain open |

See [explorer/theme evidence and reproduction](explorer-acceptance.md),
[annotation evidence](annotation-acceptance.md), [Windows paths](windows-paths.md),
[update procedure](actualizacion.md) and [Actions policy](actions-policy.md).
No deployment migration or restart is implied by these validation results.

## Work-runtime checks — 2026-10-26

Windows/Python 3.12.14: 380 source tests passed, with one native symlink privilege skip.
The installed 0.1.0a2 wheel passed the existing personal verifier, including its provider,
eight stdio tools, viewer fragments, owned integration and recovery.

`scripts/verify-work-runtime.py` passed Windows PowerShell preview/apply installation in a
synthetic path with spaces and accents, owned Augment-skill setup, the stable Python/CMD
launchers, eight work stdio tools, rejection of personal captures and real isolated provider
search/status. A second wheel built from the same reviewed code with a synthetic 0.1.0a3 version
exercised update/rollback: active-session refusal, recovery copies and preservation of notes
created before and after the update. That second version is a test fixture, not a published release.

Work annotations use scoped schema 4; personal schema 1–3 exports remain personal and retain
their existing compatibility. Cross-scope note bundles and annotation imports are refused.
Actual JetBrains/plugin acceptance remains [issue #2](https://github.com/AdanJoGoHe/Shiori/issues/2).
No Linux run, corporate data, real work-device setup, remote deployment or published-release-pair
upgrade is claimed by these checks.

## Published-release updater — 2026-10-26

411 source tests passed (one native symlink privilege skip), including channel selection,
read-only checks, download bounds/redirects, corrupt/missing/duplicate assets, network errors,
live-session refusal and preservation of edited skills. A real anonymous GitHub check returned
no published stable or prerelease; draft releases were not offered.

Installed alpha.3 passed the personal wheel verifier and the work verifier. The latter used
synthetic GitHub metadata and asset responses with a separately built synthetic stable 0.1.0
wheel: actual package installation, automatic owned-skill refresh, launcher refresh and rollback
preserved notes created before and after updating. Both the incoming release folder and install
path contained spaces and accents; this reproduces the fixed uv 0.12.15 constraint-path parsing
failure. Wheel and constraints paths are passed as encoded file URIs.

These are local synthetic update/recovery checks, not an upgrade between two published releases
or acceptance of the actual Augment IDE. Release files remain drafts until explicitly published.

## Hybrid learned workflows — 2026-10-27

461 source tests passed (one native symlink privilege skip). The 50 learning tests also passed
against the installed alpha.4 wheel, including both scopes, both export host names, read-only
previews, stale revisions, broader capabilities, foreign/edited files, interrupted activation,
bounded targets and explicit archival. Both base skills passed frontmatter validation.

The installed personal verifier passed; the work verifier passed PowerShell installation,
eight stdio tools, real isolated Basic Memory search/status and actual managed-CLI proposal,
activation and revision checks with fictitious content. Generated host files were placed only
in synthetic private directories. The research uses pinned upstream source; no external plugin
was installed/executed, no extra runtime model process or hooks were installed, and no real
corporate material was used. Application-level skill selection remains unvalidated.

## Alpha.5 release checks — 2026-10-28

Windows/Python 3.12.14: 517 source tests passed, with one native symlink privilege skip.
The 56 diary/workflow tests also passed against the installed alpha.5 wheel. Both installed
release verifiers passed: ten personal/work MCP tools, provider isolation, owned skills,
CLI recovery and managed workflow learning. Chromium acceptance passed at 1440/768/390 with
the three themes, including delayed project filters, stale task versions and inert captured text.

`scripts/verify-release-upgrade.py` installed the original alpha.4 draft bundle downloaded from
GitHub, with asset sizes/digests and bundle checksums verified, then updated to alpha.5. It checked
active-session refusal, notes and marks, explicit owned-skill refresh for local-bundle updates,
rollback without losing newer notes/journal entries, and reactivation with the recorded task state
intact. Reusing an existing saved version uses rollback; update does not overwrite its environment.
This uses two actual versioned packages, not an upgrade between two published releases: alpha.4
was a draft. All memory and host files were disposable synthetic fixtures. No Linux, real Augment
IDE/device acceptance or live personal-deployment upgrade is claimed, and no Actions were run.
