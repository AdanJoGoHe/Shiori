# Repository work

Read CONTRIBUTING.md before changing source, documentation or Git metadata. Run the local
repository checks and relevant tests on the final change before committing.

Write commit messages about the resulting behavior. Never include `CODEX` (any letter case)
in the subject, body or attribution trailers. Technical references to Codex in source and
user documentation remain valid.

Publish reusable source and synthetic examples only. Keep memory contents, runtime/configuration,
logs, credentials, audit reports and conversation handoffs outside source Git. Before changing
repository visibility or rewriting history, follow docs/publication.md and preserve a private
recovery copy. Local hooks supplement review; they cannot guarantee that a repository is safe.
