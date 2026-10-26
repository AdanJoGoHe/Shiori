import hashlib
import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "prepare_release", ROOT / "scripts/prepare-release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("Synthetic source", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="1.2.3a4"\n', encoding="utf-8")
    notes = tmp_path / "docs/releases/v1.2.3-alpha.4.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("# Synthetic release", encoding="utf-8")
    skill = tmp_path / "skills/second-brain/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Synthetic skill\n", encoding="utf-8")
    work_skill = tmp_path / "skills/shiori-work/SKILL.md"
    work_skill.parent.mkdir(parents=True)
    work_skill.write_text("Synthetic work skill\n", encoding="utf-8")
    installer = tmp_path / "scripts/install-shiori.ps1"
    installer.parent.mkdir()
    installer.write_text("# Synthetic installer\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / "second_brain-1.2.3a4-py3-none-any.whl", "w") as archive:
        archive.writestr(
            "second_brain/resources/second-brain/SKILL.md",
            skill.read_bytes().replace(b"\r\n", b"\n"),
        )
        archive.writestr(
            "second_brain-1.2.3a4.dist-info/METADATA", "Name: second-brain\nVersion: 1.2.3a4\n"
        )
        archive.writestr(
            "second_brain/resources/shiori-work/SKILL.md",
            work_skill.read_bytes().replace(b"\r\n", b"\n"),
        )
    with tarfile.open(dist / "second_brain-1.2.3a4.tar.gz", "w:gz") as archive:
        item = tarfile.TarInfo("second_brain-1.2.3a4/README.md")
        raw = b"Synthetic source"
        item.size = len(raw)
        archive.addfile(item, io.BytesIO(raw))

    def export(command, **kwargs):
        if command == ["git", "ls-files", "-z"]:
            return SimpleNamespace(stdout="README.md\0")
        assert command == [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
        ]
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(stdout="synthetic-dependency==1.0\n")

    monkeypatch.setattr(release.subprocess, "run", export)
    return tmp_path


@pytest.mark.parametrize("untracked", [False, True], ids=["modified-source", "untracked-file"])
def test_rejects_unreviewed_source_archive(bundle, untracked):
    with tarfile.open(bundle / "dist/second_brain-1.2.3a4.tar.gz", "w:gz") as archive:
        name = "unreviewed.md" if untracked else "README.md"
        item = tarfile.TarInfo("second_brain-1.2.3a4/" + name)
        raw = b"Unreviewed synthetic content"
        item.size = len(raw)
        archive.addfile(item, io.BytesIO(raw))
    with pytest.raises(ValueError, match="Untracked file|differs from reviewed"):
        release.prepare(bundle)


def test_version_mapping_assets_and_checksums(bundle):
    result = release.prepare(bundle)
    assert result["tag"] == "v1.2.3-alpha.4"
    assert result["notes"] == "docs/releases/v1.2.3-alpha.4.md"
    hashes = (bundle / "dist/SHA256SUMS").read_text().splitlines()
    assert len(hashes) == 4
    for line in hashes:
        digest, name = line.split("  ")
        assert digest == hashlib.sha256((bundle / "dist" / name).read_bytes()).hexdigest()
    assert not (bundle / "dist/RELEASE_NOTES.md").exists()


@pytest.mark.parametrize("version", ["1.2.3", "1.2.3rc1", "1.2.3a4\nunsafe"])
def test_unsupported_versions_rejected(bundle, version):
    (bundle / "pyproject.toml").write_text(f'[project]\nversion="{version}"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        release.prepare(bundle)


@pytest.mark.parametrize("failure", ["notes", "private-path", "skill"])
def test_unreviewed_or_private_artifacts_rejected(bundle, failure):
    if failure == "notes":
        (bundle / "docs/releases/v1.2.3-alpha.4.md").unlink()
    elif failure == "private-path":
        with zipfile.ZipFile(bundle / "dist/second_brain-1.2.3a4-py3-none-any.whl", "a") as archive:
            archive.writestr("second_brain/state/ledger.json", "Synthetic private state")
    else:
        (bundle / "skills/second-brain/SKILL.md").write_text("Different skill", encoding="utf-8")
    with pytest.raises(ValueError):
        release.prepare(bundle)
    assert not (bundle / "dist/SHA256SUMS").exists()


def test_workflow_permissions_and_manual_release_boundary():
    workflow = yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    ci = yaml.load((ROOT / ".github/workflows/validate.yml").read_text(), Loader=yaml.BaseLoader)
    for path in (ROOT / ".github/workflows").glob("*.y*ml"):
        triggers = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)["on"]
        assert set(triggers) <= {"workflow_dispatch", "workflow_call"}, path.name
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["publish"]["default"] == "false"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["validate"]["uses"] == "./.github/workflows/validate.yml"
    retired = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(retired["on"]) == {"workflow_dispatch"}
    assert retired["jobs"]["retired"]["if"] == "${{ false }}"
    assert set(ci["on"]) == {"workflow_call", "workflow_dispatch"}
    dispatch = ci["on"]["workflow_dispatch"]["inputs"]
    assert dispatch["platform"]["default"] == "linux"
    assert dispatch["platform"]["options"] == ["linux", "windows", "both"]
    assert dispatch["reason"]["required"] == "true"
    assert ci["permissions"] == {"contents": "read"}
    assert ci["concurrency"]["cancel-in-progress"] == "true"
    checks = ci["jobs"]["checks"]
    assert checks["timeout-minutes"] == "15"
    assert checks["strategy"]["fail-fast"] == "true"
    assert checks["strategy"]["max-parallel"] == "1"
    matrix = checks["strategy"]["matrix"]["os"]
    assert "inputs.platform == 'windows'" in matrix
    assert "inputs.platform == 'both'" in matrix
    assert "ubuntu-24.04" in matrix and "windows-2025" in matrix
    validation = workflow["jobs"]["validate"]
    assert validation["if"] == "github.ref == 'refs/heads/main'"
    assert validation["with"]["platform"] == "windows"
    for definition in [checks, workflow["jobs"]["release"]]:
        assert definition["timeout-minutes"] == "15"
        steps = definition["steps"]
        assert (
            sum(s.get("run") == "uv run --locked python scripts/check-local.py" for s in steps) == 1
        )
        cache = next(s for s in steps if s.get("uses", "").startswith("astral-sh/setup-uv@"))
        assert cache["with"] == {
            "version": "0.12.15",
            "enable-cache": "true",
            "cache-dependency-glob": "uv.lock",
            "prune-cache": "true",
        }
        for step in steps:
            if "uses" in step:
                assert len(step["uses"].rsplit("@", 1)[-1]) == 40
    assert workflow["jobs"]["release"]["runs-on"] == "ubuntu-24.04"
    job = workflow["jobs"]["release"]
    assert job["needs"] == "validate"
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["permissions"] == {"contents": "write"}
    assert job["steps"][-1]["if"] == "inputs.publish"
