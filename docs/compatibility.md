# Compatibility — 2026-10-24

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
| Work | Deployment disabled; no employer material used |
| Hooks/automatic capture | Not installed; instruction-driven retrieval/capture remains best effort |
| Stable release | Full v1/M5 gates and published-release upgrade/rollback remain open |

See [explorer/theme evidence and reproduction](explorer-acceptance.md),
[annotation evidence](annotation-acceptance.md), [Windows paths](windows-paths.md),
[update procedure](actualizacion.md) and [Actions policy](actions-policy.md).
No deployment migration or restart is implied by these validation results.
