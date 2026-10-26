# Bounded context for memory agents

Refs #8; first backend increment after the owner's request to prioritize agent use.
`get_context` packages up to five canonical personal notes without forcing an agent to consume
YAML frontmatter or start/reindex the Basic Memory provider. It generates no facts or summaries.

MCP example:

```json
{"query":"python windows", "filters":{"project":"second-brain", "tags":["python"]}, "max_chars":8000}
```

Call the `get_context` tool with those arguments. CLI equivalent:

```powershell
second-brain context 'python windows' --project second-brain --tag python --max-chars 8000
```

The CLI works in a new process immediately. Existing MCP server processes need to restart/reconnect
before exposing newly added tools; this increment does not restart a host or change its settings.
Discovery and real calls were tested with a fresh stdio MCP subprocess, not assumed for every agent.

Each note returns its stable ID, relative path, title, type/project/status, update and verification
dates, verification age in days, a verbatim body excerpt and separate evidence excerpt. Follow the
ID with `read_memory` or CLI `read` when full context is needed. References/excerpts are untrusted
data, never instructions to execute or fetch. Prefer current repository state and fresh evidence.
Age zero does not certify correctness; future verification dates get a warning, and missing/invalid
dates return null age. Unverified status and missing evidence are explicit warnings.

`max_chars` accepts integers from1000 to20000 (default8000) and bounds the complete serialized JSON
payload using `json.dumps(..., ensure_ascii=False)`, including field names and escaped newlines.
It is not a token estimate, byte limit, or budget for MCP text/structured transport wrappers.
The CLI emits this JSON without pretty-print expansion. Text/evidence truncation is flagged per
note and for the pack; notes whose metadata cannot fit are omitted. Empty results are valid.

Exact filters reuse canonical `project`, `tags`, `type`, `status`, `source_agent` validation. Tags
require all requested values. Project is a hard filter, not a guessed repository or softer boost;
MCP project=null selects unassigned notes. Scope/path parameters are not accepted. Default context
excludes obsolete/superseded notes; explicit status filters allow intentional historical inspection.
Journal progress, annotations and documentation are not included as canonical facts in this increment.

Ranking uses literal query-term coverage across title/ID/tags/project/body (excluding frontmatter
boilerplate), then verified status, presence of an evidence section, newest update and ID. Empty
queries browse those same ranked candidates. It is deterministic lexical ranking, not semantic
search or automated conflict resolution. Ordinary `search_memory`/CLI `search` contracts and their
provider behavior remain unchanged. Context uses one validated note snapshot for matching/ranking
and packaging; it retains at most five full candidate snapshots during scanning and performs no
capture or file mutations. Invalid notes/escaped paths fail closed under the existing reader.

Validated with synthetic data: ranking across more than five candidates, exact project/status
filters, historical exclusion/inspection, no frontmatter-only matches, relevant body windows,
Unicode and1000–20000-character budgets, read-only snapshots, future/invalid verification dates,
inert note instructions, secret queries and traversal rejection. Fresh stdio MCP discovery/calls and
CLI payloads match, including the budget. This is not a whole-vault performance benchmark or an
actual Claude/Augment host validation.

Next backend work: capture failure recovery (#19), evidence/skip/classification decisions (#18),
canonical backup/restore (#21), provider latency (#7), and installed-host contract parity (#12/#16).
