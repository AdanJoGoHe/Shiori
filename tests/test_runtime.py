import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from filelock import FileLock

from second_brain import runtime
from second_brain.core import Brain
from test_core import event


def bundle(root, version="1.2.3a4", constraints="filelock==4.1.0\n"):
    root.mkdir()
    wheel = root / f"second_brain-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"second_brain-{version}.dist-info/METADATA",
            f"Name: second-brain\nVersion: {version}\n",
        )
    pins = root / f"second_brain-{version}-constraints.txt"
    pins.write_text(constraints)
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in [wheel, pins]
        )
    )
    return root


@pytest.fixture
def managed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "command", lambda args: calls.append(args))
    monkeypatch.setattr(
        runtime,
        "candidate_launchers",
        lambda root, version: {
            name: (root / name).read_text(encoding="utf-8") for name in ["shiori.py", "shiori.cmd"]
        },
    )
    root = tmp_path / "Synthetic work"
    release = bundle(tmp_path / "release")
    runtime.install(root, release, apply=True)
    brain = Brain(runtime.configuration(root, "UTC"))
    brain.capture(event(scope="work"))
    return root, brain, calls


def test_preview_is_read_only_and_requires_new_target(tmp_path):
    release = bundle(tmp_path / "release")
    root = tmp_path / "work"
    result = runtime.install(root, release)
    assert result["status"] == "ready" and not root.exists()
    root.mkdir()
    with pytest.raises(ValueError, match="new directory"):
        runtime.install(root, release, apply=True)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "pins",
    [
        "-r elsewhere.txt",
        "thing @ https://example.invalid/wheel.whl",
        "thing>=1",
        "thing==1.*",
        "--index-url https://example.invalid",
    ],
)
def test_release_does_not_accept_pip_directives_or_unpinned_dependencies(tmp_path, pins):
    with pytest.raises(ValueError):
        runtime.release_bundle(bundle(tmp_path / "release", constraints=pins))


def test_corrupt_or_duplicate_release_hashes_are_rejected(tmp_path):
    release = bundle(tmp_path / "release")
    hashes = release / "SHA256SUMS"
    original = hashes.read_text()
    hashes.write_text(original + original)
    with pytest.raises(ValueError, match="duplicate"):
        runtime.release_bundle(release)
    hashes.write_text(original)
    next(release.glob("*.whl")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        runtime.release_bundle(release)


def test_update_and_rollback_preserve_notes_settings_and_stable_launcher(managed, tmp_path):
    root, brain, calls = managed
    original = brain.read("git-version")
    launcher = (root / "shiori.py").read_bytes()
    cfg = (root / "data/config.json").read_bytes()
    next_release = bundle(tmp_path / "next", "1.2.3a5")
    before = {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert runtime.change_version(root, next_release)["to"] == "1.2.3a5"
    assert before == {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    result = runtime.change_version(root, next_release, apply=True)
    assert (
        result["status"] == "updated"
        and (Path(result["recovery"]) / "memory/manifest.json").is_file()
    )
    assert runtime.manifest(root)[0]["active"] == "1.2.3a5"
    assert runtime.change_version(root, apply=True)["status"] == "rolled-back"
    assert runtime.manifest(root)[0]["active"] == "1.2.3a4"
    assert brain.read("git-version") == original
    assert (root / "shiori.py").read_bytes() == launcher
    assert (root / "data/config.json").read_bytes() == cfg
    assert any("--expect-version" in call for call in calls)


def test_failed_candidate_does_not_activate_or_replace_memory(managed, tmp_path, monkeypatch):
    root, brain, _ = managed
    previous = (root / "installation.json").read_bytes()
    content = brain.read("git-version")
    monkeypatch.setattr(
        runtime, "probe", lambda *args: (_ for _ in ()).throw(ValueError("incompatible"))
    )
    with pytest.raises(ValueError, match="incompatible"):
        runtime.change_version(root, bundle(tmp_path / "next", "1.2.3a5"), apply=True)
    assert (root / "installation.json").read_bytes() == previous
    assert brain.read("git-version") == content
    assert len(list((root / "recovery").glob("*/memory/manifest.json"))) == 1


def test_live_session_refuses_update_before_installing(managed, tmp_path):
    root, _, calls = managed
    sessions = root / "sessions"
    sessions.mkdir()
    previous_calls = len(calls)
    with FileLock(sessions / ("a" * 32 + ".lease")):
        with pytest.raises(ValueError, match="Close all"):
            runtime.change_version(root, bundle(tmp_path / "next", "1.2.3a5"), apply=True)
    assert len(calls) == previous_calls
    assert runtime.manifest(root)[0]["active"] == "1.2.3a4"


def test_launcher_write_failure_restores_owned_files_and_keeps_active_version(
    managed, tmp_path, monkeypatch
):
    root, _, _ = managed
    before = {
        name: (root / name).read_bytes()
        for name in ["shiori.py", "shiori.cmd", "installation.json"]
    }
    monkeypatch.setattr(
        runtime,
        "candidate_launchers",
        lambda *args: {
            "shiori.py": "# new synthetic launcher\n",
            "shiori.cmd": "new synthetic command\n",
        },
    )
    write = runtime.atomic_write

    def fail(path, content):
        if path == root / "shiori.cmd" and content == "new synthetic command\n":
            raise OSError("Synthetic write failure")
        write(path, content)

    monkeypatch.setattr(runtime, "atomic_write", fail)
    with pytest.raises(OSError, match="Synthetic"):
        runtime.change_version(root, bundle(tmp_path / "next", "1.2.3a5"), apply=True)
    assert all((root / name).read_bytes() == raw for name, raw in before.items())
    assert runtime.manifest(root)[0]["active"] == "1.2.3a4"


@pytest.mark.parametrize("version", ["1.2.3", "1.2.3b1", "1.2.3rc2"])
def test_release_runtime_accepts_future_stable_beta_and_rc_versions(tmp_path, version):
    assert runtime.release_bundle(bundle(tmp_path / "release", version))["version"] == version


@pytest.mark.parametrize("mutation", ["launcher", "scope", "paths", "missing-data"])
def test_changed_installation_is_refused_without_reinitializing(managed, mutation, tmp_path):
    root, _, _ = managed
    if mutation == "launcher":
        (root / "shiori.py").write_text("edited")
    elif mutation == "missing-data":
        # Keep the old data and simulate temporarily unavailable managed roots.
        shutil.move(root / "data/vault", tmp_path / "unavailable-vault")
        shutil.move(root / "data/state", tmp_path / "unavailable-state")
    else:
        path = root / "data/config.json"
        cfg = json.loads(path.read_text())
        cfg["scope" if mutation == "scope" else "vault_path"] = (
            "personal" if mutation == "scope" else str(tmp_path / "elsewhere")
        )
        path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        runtime.manifest(root)
    if mutation == "missing-data":
        assert not (root / "data/vault").exists() and not (root / "data/state").exists()


def test_augment_setup_is_explicit_and_never_overwrites_foreign_or_edited_skill(managed, tmp_path):
    root, _, _ = managed
    skills_dir = tmp_path / "synthetic-home/.augment/skills"
    result = runtime.augment(root, skills_dir)
    assert result["name"] == "shiori_work" and not skills_dir.exists()
    result = runtime.augment(root, skills_dir, apply=True)
    target = Path(result["skill"])
    assert target.is_file() and '"scope": "work"' in target.read_text()
    runtime.augment(root, skills_dir, apply=True)
    target.write_text("edited")
    with pytest.raises(ValueError, match="unowned or edited"):
        runtime.augment(root, skills_dir, apply=True)
    assert target.read_text() == "edited"


def test_managed_cli_cannot_override_config(managed):
    root, _, _ = managed
    for arguments in [
        ["serve", "--config=other.json"],
        ["--config", "other.json", "serve"],
        ["restore"],
    ]:
        with pytest.raises(ValueError):
            runtime.run(root, arguments)


def test_private_root_refuses_git_and_home(tmp_path):
    (tmp_path / ".git").mkdir()
    for root in [tmp_path / "new", Path.home()]:
        with pytest.raises(ValueError):
            runtime.private_root(root)
