# Manual release workflow

`Release` is a manually dispatched GitHub Actions workflow. It has no push/tag trigger;
adding or merging the workflow does not create a tag or a release. An original local publication
attempt was blocked by automatic permission review; the workflow is not a way to retry a denied
operation. A new publication needs the owner's current authorization and applicable access checks.

Once reviewed/merged into main:

1. Open repository **Actions → Release → Run workflow** and select **main**.
2. Leave **publish=false** to create a draft. Select true only when you explicitly want publication
   after validation. A published alpha is always marked prerelease.
3. On main only, the workflow first validates Windows through `validate.yml`, including isolated
   wheel acceptance. Dispatches on other branches skip both jobs before allocating runners.
4. A Linux release job runs the local source checks, builds the exact dispatched commit, audits
   the bundle and tests that wheel, then creates a version-derived tag/draft with five named assets (wheel, source, constraints, Windows installer and checksums). The tag is
   derived from `pyproject.toml` (`0.1.0a1` → `v0.1.0-alpha.1`); matching notes must exist under
   `docs/releases/`. Other version schemes require an explicit mapping update before use.
5. Review the draft's wheel, source archive, pinned constraints and SHA256SUMS. Publish the draft
   through GitHub when ready, if publish was false.

Only the release job requests `contents:write`; validation is read-only. It uses GitHub's built-in
GITHUB_TOKEN, not a local credential or stored personal access token. Repository/organization tag
or token policies may still reject writes; this workflow does not change or bypass those policies.
Checkout credentials are not persisted; dispatch inputs are not interpolated into shell code.

The release job is main-only and waits for Windows validation; its own checks validate Linux. Runs are serialized without
cancelling in-progress publication. Existing tags/releases are rejected rather than overwritten.
If creation/upload fails partway, inspect any tag/draft manually before retrying; the workflow does
not delete, replace or clobber partial outputs. Skipped release jobs from non-main dispatches do not
mean a release was created. Publishing never runs unless validation and draft creation succeed.

`scripts/prepare-release.py` makes no remote writes. It checks the version, required release notes,
wheel metadata/canonical skills, source links and unsafe/private artifact directories; emits four
SHA-256 hashes and a fixed asset selection. This is a path/structure audit, not a general secret
detector. Only synthetic fixtures belong in source. No vault, local configuration, logs or session
artifacts are uploaded. Constraints come from the locked runtime dependencies.

Local validation uses the actual built artifacts plus table-driven synthetic tests for version
mapping, checksums, missing notes, modified skills and private paths. Workflow tests enforce manual
dispatch, default draft, main-only jobs, reusable validation and scoped permissions. A parsed YAML
file and local script run are not evidence of a successful hosted release; no release workflow was
dispatched during implementation.

References: [reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
and [GitHub CLI release creation](https://cli.github.com/manual/gh_release_create).


## Cost policy

Routine PRs/pushes use [local validation](actions-policy.md), not Actions. Release still validates
both operating systems, with two jobs instead of three: one Windows validator and the Linux job
that also prepares the actual release wheel. Each runner job has a15-minute timeout and pruned uv
cache keyed by the lockfile/platform. Validation supersession cancels stale checks; release
publication remains serialized without cancellation. Actions were not dispatched to test this
policy; static/local checks do not establish hosted success or actual billing savings.

## Local release without Actions

With current owner authorization, a Windows alpha can also be prepared and published locally.
Bump the package and lock versions, add matching release notes, run the source/policy/secret
checks, build and run `scripts/prepare-release.py`. Test the exact installed wheel with both
release verifiers and the diary browser workflow. `scripts/verify-release-upgrade.py` checks a
real older bundle against the candidate, including notes, marks, skill refresh and rollback,
using disposable memory only. It does not publish or update an existing deployment.

Merge the reviewed release commit, create a draft targeting that exact commit and upload only
the five allowlisted assets. Compare uploaded sizes/digests with the tested files before publishing
as a prerelease. Keep older drafts/assets intact. Verify the public tag and anonymous downloads
after publication. Report the platform actually tested; local Windows checks do not establish
Linux or application-level Augment acceptance. This route does not dispatch the hosted workflow.
