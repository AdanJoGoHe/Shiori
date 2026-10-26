# Publication boundary

Shiori publishes reusable source, maintained documentation and synthetic fixtures. Memory vaults,
state, indexes, deployment configuration, credentials, journals, capture payloads, audit reports,
conversation handoffs and screenshots of personal data stay outside source Git and release assets.
Examples use placeholders and documented synthetic addresses. Being readable text is not permission
to publish it. A secret scanner supplements human review; a passing result does not prove absence
of private information, customer material or proprietary content.

## Before publication

1. Preserve a private recovery copy outside the checkout. Record the reviewed tree and remote refs.
2. Review every source path, documentation/example and staged diff. Remove temporary session documents,
   obsolete bootstrap tools and duplicated planning prompts; repair encoding instead of hiding warnings.
3. Run the repository policy with Gitleaks, source checks, and clean-package verification. Review the
   final wheel/sdist contents too. Use synthetic deployments, never a live memory export.
4. Review the **GitHub surface**, not just main: all branches/tags/PR refs, issues, comments/reviews,
   wikis, releases/assets, Actions logs/artifacts/caches and repository settings. Keep private audit
   reports outside Git. Record any surface that could not be inspected; do not mark it cleared.
5. Review history and commit messages. A public initial root should describe the product, for example
   `Initial Shiori source`. Verify it has no parents and that the published branch contains only that
   root. Keep subsequent messages aligned with CONTRIBUTING.md.
6. Make the chosen repository public only after its exact contents and metadata have been reviewed.
   Confirm anonymous access and visibility afterward. Publishing source does not certify production
   readiness, publish a package/release or grant an open-source license.

## History has more than one surface

Squashing main does not erase PR references, other branches, forks, cached commit views, clones,
Actions logs or issue history. Rewriting Git alone must never be described as complete erasure.
For an isolated public starting point, create a new repository from the reviewed parentless tree
and retain the original private repository for planning/history. Copy only reviewed public metadata.
For an in-place rewrite, audit the historical GitHub surfaces as well; affected sensitive data may
need credential rotation and GitHub Support. Do not delete a repository or its logs as a shortcut.

After a rewrite, use a fresh clone for new work. Keep old clones/backups private and port reviewed
patches rather than merging old branches. The local checkout can retain the same filesystem path
and integration configuration after its Git source is reconciled; do not move or reset a live vault.

## References

- [GitHub visibility consequences](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
- [GitHub sensitive-data removal and PR references](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [Gitleaks](https://github.com/gitleaks/gitleaks)
