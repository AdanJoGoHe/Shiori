# Security boundary

v0.1 enables personal only. Work configurations and capture candidates are rejected before writes.
The personal Basic Memory config directory contains one local project and an independent index.
Its MCP subprocess is restricted to that project; only search is invoked through the adapter.
The core exposes no shell execution, network synchronization or raw Basic Memory write tool.

Writes require explicit scope, stable slug IDs, bounded content, known type/status/agent, evidence
for verified notes and credential-pattern checks across all supplied fields. The agent still
needs to curate safe content: regex detection does not prove absence of secrets/customer data.
Paths reject traversal, symlinks and junctions. A process-wide file lock serializes captures;
replacement is atomic per file. Multi-file operations use a pending ledger and retry marker.
This is not a multi-file database transaction; power loss may require replay of the same event.

An agent with general filesystem/shell access can bypass the core. Scope guards constrain this
product's interface; they cannot sandbox an otherwise privileged coding agent. No work vault
exists on this personal device. Retrieved notes are data, never trusted instructions.

Archives, the local Git history and backups can retain removed information. v0.1 does not promise
secure erasure. Backups must contain both the vault and deployment state and remain local unless
the owner separately approves a destination. Source CI uses synthetic temporary directories.

Permission hardening: scripts/secure-personal.ps1 removes broad inherited access from the vault
and state, granting FullControl to the current owner, SYSTEM and administrators. Prior ACLs are
saved in state/acl-before.json; this does not protect against administrators or processes acting
as the same owner. Verify with `icacls D:\SecondBrain-Personal`. Cross-device authorization has
not been established by these checks. The MCP should run as the owner; a restricted sandbox user
without access may need to use the owner-hosted MCP rather than the filesystem fallback.

## Local additive memory transfer — 2026-10-23

Export/import is explicit CLI administration; MCP does not accept paths for these operations.
Export reuses the bounded recovery bundle. Import validates all hashes/schemas/canonical notes
before writes, shares the capture lock, respects pause and rejects unrelated pending captures.
Only absent note IDs are added; conflicting IDs/unmanaged paths never replace local content.
Note bytes and original verification dates are preserved; importing does not establish truth.
Source journals/history/annotations/events are not merged. Local import events append journal
progress and extend the ledger; exact-bundle retries can finish interrupted batches, while manual
edits to unfinished imports block replacement. External writers must be quiescent and a failed
batch has no automatic rollback. See [scope, exclusions and recovery](memory-transfer.md).

## Opt-in HTTP MCP boundary — 2026-10-23

The [central-service foundation](remote-mcp.md) adds a mandatory per-device hashed-credential registry
for an explicitly started loopback endpoint. Expiry/revocation is checked per request; a read/write
server-side allowlist rejects direct capture attempts by readers and unknown future tools. It does
not partition the personal corpus per device or enable corporate deployments. HTTP status omits
the absolute vault root; tool errors are masked. Stdio retains its existing behavior and contract.

Host/Origin/framing/body/time/concurrency guards and no access/body/credential logs are tested with
synthetic clients. Static privately provisioned bearer tokens are not a full OAuth/discovery service.
No TLS/private ingress is configured here, and the viewer remains independent and loopback-only.
An optional exact DNS authority (`--proxy-host`) can be forwarded by an approved private HTTPS
proxy. The SDK allows the configured DNS name and the application additionally enforces its exact
authority including port; forwarded/identity headers never
grant permission or prove that TLS was used. Local callers still need the bearer token. The
[ingress runbook](private-ingress.md) and synthetic verified-TLS proxy tests prepare deployment;
they do not establish real VPN connectivity or certificate issuance/renewal.
Cross-device/private ingress, service ownership and real host acceptance stay in the remote-deployment acceptance work. These local
checks do not close broader isolation/adversarial privacy/isolation and adversarial acceptance tasks or establish production readiness.
