import json
import sys
import tomllib
from pathlib import Path

import pytest

from second_brain.install import install, uninstall, upgrade


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "config.toml").write_text('[mcp_servers.existing]\ncommand = "other"\n')
    (codex / "AGENTS.md").write_text("Existing instructions\n")
    state = tmp_path / "state"
    state.mkdir()
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "personal",
                "vault_path": str(tmp_path / "vault"),
                "state_path": str(state),
                "timezone": "Europe/Madrid",
            }
        )
    )
    return config, codex


def test_install_uninstall_restores_original(deployment):
    config, codex = deployment
    originals = {name: (codex / name).read_bytes() for name in ["config.toml", "AGENTS.md"]}
    assert install(config)["status"] == "installed"
    server = tomllib.loads((codex / "config.toml").read_text())["mcp_servers"][
        "second_brain_personal"
    ]
    assert server["command"] == str(Path(sys.executable).absolute()).replace("\\", "/")
    assert install(config)["status"] == "already installed"
    assert uninstall(config)["status"] == "uninstalled"
    for name, data in originals.items():
        assert (codex / name).read_bytes() == data
    assert not (codex / "skills/second-brain/SKILL.md").exists()
    assert install(config)["status"] == "installed"


def test_uninstall_preserves_later_settings(deployment):
    config, codex = deployment
    install(config)
    target = codex / "config.toml"
    target.write_text(target.read_text() + '\n[mcp_servers.later]\ncommand = "later"\n')
    assert uninstall(config)["status"] == "uninstalled"
    assert "later" in target.read_text() and "existing" in target.read_text()
    assert "second_brain_personal" not in target.read_text()


def test_modified_skill_is_preserved(deployment):
    config, codex = deployment
    install(config)
    skill = codex / "skills/second-brain/SKILL.md"
    skill.write_text(skill.read_text() + "\nUser additions\n")
    assert uninstall(config)["status"] == "manual reconciliation needed"
    assert "User additions" in skill.read_text()


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_upgrade_preview_apply_and_uninstall(deployment, monkeypatch):
    import second_brain.install as installer

    config, codex = deployment
    original = {name: (codex / name).read_bytes() for name in ["config.toml", "AGENTS.md"]}
    install(config)
    skill = codex / "skills/second-brain/SKILL.md"
    old_skill = skill.read_bytes()
    old_manifest = (config.parent / "state/install-manifest.json").read_bytes()
    monkeypatch.setattr(installer, "packaged_skill", lambda: "# New synthetic skill\n")
    monkeypatch.setattr(installer.sys, "executable", str(config.parent / "new-runtime/python"))
    before = snapshot(config.parent)
    preview = upgrade(config)
    assert preview["status"] == "upgrade available" and not preview["applied"]
    assert set(preview["changes"]) == {str(codex / "config.toml"), str(skill)}
    assert snapshot(config.parent) == before
    result = upgrade(config, apply=True)
    assert result["status"] == "upgraded" and result["restart_required"]
    recovery = Path(result["recovery"])
    assert (recovery / "SKILL.md").read_bytes() == old_skill
    assert (recovery / "install-manifest.json").read_bytes() == old_manifest
    assert skill.read_text() == "# New synthetic skill\n"
    assert "new-runtime/python" in (codex / "config.toml").read_text()
    assert "config.json" in (codex / "config.toml").read_text()
    after = snapshot(config.parent)
    assert upgrade(config, apply=True)["status"] == "up to date"
    assert snapshot(config.parent) == after
    assert uninstall(config)["status"] == "uninstalled"
    for name, raw in original.items():
        assert (codex / name).read_bytes() == raw
    assert not skill.exists()


def test_upgrade_preserves_later_settings_and_crlf(deployment, monkeypatch):
    import second_brain.install as installer

    config, codex = deployment
    install(config)
    target = codex / "config.toml"
    later = b'\r\n[mcp_servers.later]\r\ncommand = "later"\r\n'
    raw = target.read_bytes().replace(b"\r\n", b"\n")
    target.write_bytes(b"\xef\xbb\xbf" + raw.replace(b"\n", b"\r\n") + later)
    agents = codex / "AGENTS.md"
    agents.write_bytes(agents.read_bytes() + b"\nUser instructions\n")
    monkeypatch.setattr(installer.sys, "executable", str(config.parent / "new/python"))
    assert upgrade(config, apply=True)["status"] == "upgraded"
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    assert target.read_bytes().endswith(later)
    assert b"\n" not in target.read_bytes().replace(b"\r\n", b"")
    assert uninstall(config)["status"] == "uninstalled"
    assert target.read_bytes().endswith(later)
    assert b"existing" in target.read_bytes()
    assert agents.read_bytes().endswith(b"\nUser instructions\n")
    assert b"SECOND BRAIN" not in agents.read_bytes()


@pytest.mark.parametrize("target", ["skill", "config", "agents", "duplicate", "manifest", "backup"])
def test_upgrade_conflicts_do_not_mutate_targets(deployment, monkeypatch, target):
    import second_brain.install as installer

    config, codex = deployment
    install(config)
    manifest_path = config.parent / "state/install-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if target == "skill":
        path = codex / "skills/second-brain/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nUser additions")
    elif target in {"config", "agents", "duplicate"}:
        path = codex / ("AGENTS.md" if target == "agents" else "config.toml")
        raw = path.read_bytes()
        path.write_bytes(
            raw + b"\n# BEGIN SECOND BRAIN PERSONAL\n"
            if target == "duplicate"
            else raw.replace(b"# END SECOND BRAIN PERSONAL", b"# END USER BLOCK")
        )
    elif target == "manifest":
        manifest["skill"] = str(config.parent / "unrelated.md")
        manifest_path.write_text(json.dumps(manifest))
    else:
        Path(manifest["entries"][0]["backup"]).write_text("modified backup")
    monkeypatch.setattr(installer, "packaged_skill", lambda: "# New skill\n")
    before = snapshot(config.parent)
    for apply in [False, True]:
        with pytest.raises(ValueError):
            upgrade(config, apply=apply)
        assert snapshot(codex) == {
            k[len(".codex/") :]: v for k, v in before.items() if k.startswith(".codex/")
        }
        assert manifest_path.read_bytes() == before["state/install-manifest.json"]


def test_upgrade_write_failure_restores_previous_files(deployment, monkeypatch):
    import second_brain.install as installer

    config, codex = deployment
    install(config)
    monkeypatch.setattr(installer, "packaged_skill", lambda: "# New skill\n")
    monkeypatch.setattr(installer.sys, "executable", str(config.parent / "new/python"))
    before = snapshot(codex)
    manifest_path = config.parent / "state/install-manifest.json"
    old_manifest = manifest_path.read_bytes()
    write = installer.atomic_write

    def fail_manifest(path, text):
        if path == manifest_path:
            raise OSError("Synthetic manifest write failure")
        write(path, text)

    monkeypatch.setattr(installer, "atomic_write", fail_manifest)
    with pytest.raises(OSError, match="previous files restored"):
        upgrade(config, apply=True)
    assert snapshot(codex) == before
    assert manifest_path.read_bytes() == old_manifest
    assert list((config.parent / "state/backups").glob("upgrade-*/install-manifest.json"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows short-name aliases")
def test_upgrade_accepts_windows_short_path_alias(deployment, monkeypatch):
    import ctypes
    import second_brain.install as installer

    config, codex = deployment
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(str(config.parent), buffer, len(buffer))
    assert 0 < size < len(buffer)
    alias = Path(buffer.value)
    if alias == config.parent:
        pytest.skip("Short names are disabled for the temporary directory")
    config = alias / "config.json"
    values = json.loads(config.read_text())
    values["state_path"] = str(alias / "state")
    config.write_text(json.dumps(values))
    monkeypatch.setattr(Path, "home", lambda: alias)
    install(config)
    assert upgrade(config)["status"] == "up to date"
    monkeypatch.setattr(installer, "packaged_skill", lambda: "# New synthetic skill\n")
    assert upgrade(config, apply=True)["status"] == "upgraded"
    assert uninstall(config)["status"] == "uninstalled"
