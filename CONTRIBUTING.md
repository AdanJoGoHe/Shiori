# Contributing

Use Python 3.12 and install development dependencies with `uv sync --locked --extra dev`.
Source and tests use synthetic data. Keep vaults, deployment configuration, credentials,
logs, audit reports, private session URLs and conversation handoffs outside this repository.
Private launcher integrations, deployment manifests and local process-management bridges belong
in separate private repositories.
Read [the publication boundary](docs/publication.md) before changing visibility or Git history.

## Local checks

```powershell
.\.venv\Scripts\python.exe scripts/check-local.py
.\.venv\Scripts\python.exe scripts/check-repository.py --secrets
```

The first command checks tracked working files, lint, formatting and tests. The second also
requires [Gitleaks](https://github.com/gitleaks/gitleaks), available on PATH or configured locally:

```powershell
git config --local shiori.gitleaks 'C:/Tools/gitleaks/gitleaks.exe'
git config --local core.hooksPath .githooks
```

Install Gitleaks from its official release and verify the archive against that release's SHA256
checksums. The publication preparation uses version 8.30.1. Local settings contain machine paths;
they are not committed. After cloning, each contributor must enable the hooks in their own clone.
Review an existing `core.hooksPath` before changing it; integrate existing hooks rather than replacing them.

The pre-commit hook checks **all exact staged blobs**, including partially staged files, and
runs Gitleaks with redacted output. It rejects unexpected file types/directories, binary or invalid
UTF-8 text, hidden controls, common broken-encoding sequences, personal Windows user paths,
links/submodules, oversized files and active/external SVG elements. New file formats require an
explicit allowlist change and review. The default 2 MiB file limit keeps binaries/build output out.
Hooks fail closed if a required tool or Git object cannot be read. They run locally, without Actions.

## Commits and review

Commit messages describe the resulting behavior, for example `fix: preserve notes during import`.
Do not include `CODEX` in any letter case in the subject, body or attribution trailers. The
commit-msg hook checks the complete message. Product references in code/docs remain legitimate.
Use focused branches and PRs, report checks actually run, and describe privacy/rollback implications.
A reviewer must check file names, staged diff, examples and prose for accidental personal content,
raw prompts, stale session text and unsupported claims. Automated scans cannot decide these things.

Local hooks can be bypassed and do not protect GitHub API/web edits or remote squash messages.
Review the final title/message before every merge or direct remote write. Never restore old history
by merging an old branch into a cleaned public repository; port reviewed changes individually.

## Hosted checks

Routine pushes and PRs must not start Actions. Use local source/package/browser checks and record
actual evidence for the final commit. Exceptional hosted validation needs explicit authorization
for that run and a reason/platform. See [Actions policy](docs/actions-policy.md).
