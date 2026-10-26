# Roadmap

Shiori is a personal alpha. Its current package is `0.1.0a1`; that is independent of the version
of earlier planning specifications. Implemented features include local notes/journal, bounded MCP
context, classification/retry recovery, the browser library and marked-fragment retrieval, themes,
owned integration updates, backup/restore and strictly additive note transfer.

## Priorities

1. Finish privacy/isolation and adversarial acceptance; keep corporate deployments disabled.
2. Verify full local lifecycle and recovery from the actual host, then published-version upgrades
   and rollback. Do not infer these results from unit tests or synthetic protocol clients.
3. Prepare a release from the reviewed package, compatibility limits and reproducible checks.
4. Keep remote MCP optional: authenticated loopback foundation exists; private ingress, service
   lifecycle and actual two-device acceptance remain separate work.
5. Add host hooks only after real event/continuation support is demonstrated. Claude/Augment,
   graph/timeline and other unused-host features follow demonstrated user need.

Report new public tasks and acceptance criteria in [GitHub Issues](https://github.com/AdanJoGoHe/Shiori/issues).
Historical `SB-*` planning IDs remain references; no milestone is complete merely because a task
has source code. [Compatibility](compatibility.md), [test reproduction](test-report.md), and
[the current scope](specification.md) distinguish shipped behavior from unfinished acceptance.
