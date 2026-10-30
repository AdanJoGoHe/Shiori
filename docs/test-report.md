# Validation and reproduction

Source checks, installed-package acceptance, browser workflows and actual-host acceptance prove
different things. Report the commands, platform, commit and result actually observed for each
change. Use synthetic deployments and fixtures; keep private reports outside source Git.

## Source

```powershell
uv sync --locked --extra dev
.\.venv\Scripts\python.exe scripts/check-local.py
.\.venv\Scripts\python.exe scripts/check-repository.py --secrets
```

These check repository policy, Ruff lint/format, pytest and CLI help. Gitleaks setup is described
in [CONTRIBUTING](../CONTRIBUTING.md). A native Windows symlink test can skip when the current
account lacks symlink privileges; retain that limitation in the result. Windows tests do not
establish Linux or physical MSIX/other-host acceptance.

## Installed package

Build from the exact reviewed source, install the resulting wheel with its locked constraints
in a separate environment, and run `scripts/verify-release.py` from that interpreter outside the
checkout. [Actions policy](actions-policy.md) contains the commands. The verifier requires a
non-editable package and checks actual CLI/MCP, isolated provider, owned integration, viewer,
marked fragments, transfer and recovery against disposable synthetic storage. Source and package
bytes must match the reviewed artifacts. No live owner vault is needed.

## Browser

Use `scripts/demo-viewer.py` for a synthetic preview. Reproduce the assembled workflows with
`scripts/check-explorer-workflow.py` and `scripts/check-annotation-workflow.py`; their companion
Node scripts require Playwright and a supported browser installed for the developer environment.
See [explorer acceptance](explorer-acceptance.md), [annotation acceptance](annotation-acceptance.md)
and the scripts' `--help` for environment requirements and precise scope. Browser/host checks are
separate from `check-local.py`; a unit-test pass does not imply they ran.

## Current limits

The agent-CLI baseline at `346a0db` (2026-10-30) passed 551 local tests with one Windows
symlink-privilege skip on Python 3.12.14. Its 34 new tests also passed against an installed wheel,
along with personal/work release verifiers. These results are later than published alpha.5;
dated evidence in [compatibility](compatibility.md) does not cover later changes automatically.
This repository does not claim full stable v1 acceptance,
Claude/Augment real-host integration, physical mobile/IME acceptance, an actual two-device remote
installation, or upgrade/rollback between two published releases. Hosted Actions are exceptional;
follow [the manual release procedure](release-workflow.md) when a release is intentionally prepared.
