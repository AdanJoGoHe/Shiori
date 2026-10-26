# Architecture

Agent -> Shiori MCP/CLI -> validated Markdown + local ledger and journal.
Search also consults an isolated Basic Memory local MCP subprocess, with bounded timeout and
filesystem fallback. The provider gets read queries only. Canonical note reads validate scope
and credential patterns again. Basic Memory's index is rebuildable; Markdown is authoritative.

Personal deployment only in v0.1. One core can later support a separately installed work profile;
enabling it requires explicit authorization and verified boundaries on the approved device.
No model calls, host hooks or background collectors are launched by the core.
