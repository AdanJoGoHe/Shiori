# Report significant actions

Check `memory_status.agent_log` for availability and activation in the connected work profile.
Use `record_agent_action` with its advertised schema for a reviewed action when the log is
enabled. Activation is an explicit user action. Keep one stable session ID and unique event IDs.
If status includes `session_policy`, record only work the user assigned to that session. Match
its ID, agent, project and allowed kinds. Send an empty context, concise reviewed summaries
and commands only for command kinds. Remove query strings and fragments from reviewed URL
references for found links or visits. Use file references for file changes. An expired policy
ends new capture for that session.
For a checkpoint action, use its event ID, agent and task project, and leave room for the task
and journal references. The checkpoint adds those references.

Distinguish proposed, attempted and executed commands, and found links from visited pages.
Use outcome `unknown` for uncertain effects and null occurrence time when unknown. Coverage is
`reported`. Curate and redact action text. Link a committed journal event with a
`journal-event` reference instead of capturing progress for each command.

Use `read_agent_log` for actions and `read_journal` for outcomes. On an uncertain log write,
check the exact event ID, then retry the original payload as needed. A log retry is a write to
the log. Keep the underlying action out of the retry. See [Recovery](recovery.md) for CLI access.
