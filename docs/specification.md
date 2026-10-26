# Shiori — implementation scope

This document describes the current personal alpha. The earlier v1.1 planning document was a
broader design target, not proof of shipped integrations. The user guide and tested interfaces
define current operation; [the roadmap](roadmap.md) tracks future work.

## Product

A local library for technical knowledge, documentation and work journals. People and agents can
retrieve useful commands, addresses, paths and decisions with their evidence and context. The
current deployment is personal only; corporate/customer data belongs outside this deployment.

## Canonical storage and retrieval

Validated Markdown notes are authoritative. The core owns writes, revisions, event identifiers,
the daily journal and retry ledger. Basic Memory is a separately scoped, rebuildable local index;
provider failure preserves canonical retrieval. Metadata filters and bounded context packs give
agents small results rather than entire vault dumps. Retrieved notes remain untrusted data.

Captures declare personal scope, stable note/event IDs, source and status. Verified notes require
evidence. Classification previews a save/update/journal-only/skip/deny decision; it is not semantic
privacy enforcement. Exact retries are deduplicated and unfinished writes remain inspectable.

## Interfaces

- CLI: `shiori`, with the compatible `second-brain` alias and `second_brain` Python module.
- Codex: local stdio MCP and the portable `second-brain` skill, with owned integration installation,
  upgrade preview/apply, backups, conflict refusal and uninstall that preserves unrelated settings.
- Library: loopback browser UI with document search, metadata filters, three themes, Markdown reader,
  colored text marks, categories and named fragments with context and copy/navigation controls.
- Optional authenticated HTTP MCP foundation: explicitly started loopback service, per-device hashed
  token registry and read/write tool allowlists. Private HTTPS/VPN and real two-device operation
  remain deployment acceptance work; installing the package activates no remote access.

## Recovery and transfer

Backup writes a new private bundle. Restore creates a separate paused deployment. Import previews
then adds only absent canonical notes; duplicate/conflicting IDs never overwrite local content.
Source journal/history/annotations/events remain separate rather than silently merging. Notes keep
original bytes and verification dates. External writers must be stopped during recovery operations.
See [transfer](memory-transfer.md), [recovery](backup-restore.md) and [upgrades](actualizacion.md).

## Boundaries and acceptance

The core exposes no arbitrary shell execution or background collectors. Hook-driven automatic
capture, Claude/Augment real-host integration, corporate deployments, graph/timeline and stable
release acceptance are unfinished. A synthetic protocol test is not proof of an actual host/device.
Cross-file writes are recoverable but not a power-loss transaction. See [security](security.md)
and [compatibility](compatibility.md) for limits.

Source and release assets contain synthetic fixtures only. Development uses local checks; hosted
validation is exceptional and explicitly authorized. Public-repository preparation follows
[the publication boundary](publication.md); it does not migrate installed data or configurations.

## Technical references

- [Architecture](architecture.md), [user guide](guia-de-usuario.md), [test reproduction](test-report.md).
- [MCP context](agent-context.md), [capture policy](capture-quality.md), [retry recovery](capture-recovery.md).
- [Library](viewer.md), [remote MCP](remote-mcp.md), [branding/compatibility identifiers](branding.md).
