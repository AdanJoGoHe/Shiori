# Operations

Use `second-brain doctor` for schema validation and pending event counts, `status` for pause state.

For indexed retrieval, MCP `memory_status.index` reports the last unfiltered search attempt;
it is not a live health check and CLI status does not share that process-local observation.
See [provider search and diagnostic codes](provider-search.md).
Use `doctor --provider` or MCP `memory_status(check_provider=true)` for an explicit live
project-status probe without reindexing. This returns observed file counts, not index freshness.
An unavailable provider makes the opted-in CLI check exit1 with JSON; ordinary doctor is unchanged.
Pause suppresses writes but keeps retrieval. A failed capture must not interrupt the main task.
Retry the exact payload with its original event ID; changing the payload requires a new event ID.
Store only approved minimal event files and remove them after completion; they are not transcripts.

Recovery: pause capture, close MCP clients and the viewer, then use `backup --output` with a new
private destination. `restore --input --destination` creates a separate paused deployment;
it does not replace existing data or select a host. See [backup/restore](backup-restore.md) for
limits and excluded host settings, documentation roots and original pending-capture JSON.
Bundles are plaintext, not sanitized exports. Avoid automatic remote backup.

Uninstall preserves notes, state and recovery backups. Restart Codex after installation/removal.
The local Python runtime and virtual environment must stay at their configured paths. Recreate
the environment from pyproject.toml if needed; revise the owned MCP entry if the workspace moves.
