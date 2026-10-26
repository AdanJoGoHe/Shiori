"""Synthetic alias-resolution regression; not physical MSIX-host acceptance."""

import json
from pathlib import Path

import pytest

from second_brain.catalog import Catalog
from second_brain.core import load_config, scoped_path
from second_brain.paths import diagnose, repair
from test_core import brain as brain, event


def test_catalog_keeps_registered_notes_when_root_resolution_changes(brain, tmp_path, monkeypatch):
    brain.capture(event())
    expected = brain.read("git-version")
    physical = brain.vault
    nominal = tmp_path / "virtual-local" / "vault"
    nominal.mkdir(parents=True)
    brain.vault = nominal
    original = Path.resolve

    def redirected(path, *args, **kwargs):
        if path.is_relative_to(nominal):
            return original(physical / path.relative_to(nominal), *args, **kwargs)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    assert len(brain.ledger()["notes"]) == 1
    result = Catalog(brain).snapshot("note")
    assert [row["id"] for row in result["items"]] == ["note:personal:git-version"], result["errors"]
    assert brain.read("git-version") == expected


def deployment(brain, tmp_path):
    brain.capture(event())
    from second_brain.viewer import Viewer

    viewer = Viewer(brain)
    doc = viewer.content("note:personal:git-version")
    quote = "git --version"
    start = doc["text"].index(quote)
    viewer.save_annotation(
        {
            "document_id": doc["item"]["id"],
            "revision": doc["revision"],
            "start": start,
            "end": start + len(quote),
            "quote": quote,
            "color": "green",
            "tags": ["comando"],
        }
    )
    config = tmp_path / "selected.json"
    config.write_text(
        json.dumps({**brain.config, "schema_version": 1, "custom": {"keep": "unchanged"}}),
        encoding="utf-8",
    )
    return config


def virtualize(brain, tmp_path, monkeypatch, coherent):
    mapping = {}
    for key, target in [("vault_path", brain.vault), ("state_path", brain.state)]:
        nominal = tmp_path / "virtual-local" / key
        nominal.mkdir(parents=True, exist_ok=True)
        mapping[nominal] = target
    original_resolve, original_stat = Path.resolve, Path.stat

    def redirected(path, *args, **kwargs):
        for nominal, physical in mapping.items():
            if path.is_relative_to(nominal) and (coherent or path != nominal):
                return original_resolve(physical / path.relative_to(nominal), *args, **kwargs)
        return original_resolve(path, *args, **kwargs)

    def stat(path, *args, **kwargs):
        for nominal, physical in mapping.items():
            if path.is_relative_to(nominal) and path != nominal:
                return original_stat(physical / path.relative_to(nominal), *args, **kwargs)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(Path, "stat", stat)
    return {field: str(nominal) for field, nominal in zip(["vault_path", "state_path"], mapping)}


def snapshot(brain):
    return {
        path: path.read_bytes()
        for root in [brain.vault, brain.state]
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "coherent", [True, False], ids=["coherent-alias", "root-child-disagreement"]
)
def test_preview_and_explicit_repair_preserve_store_bytes(brain, tmp_path, monkeypatch, coherent):
    config = deployment(brain, tmp_path)
    before = snapshot(brain)
    nominal = virtualize(brain, tmp_path, monkeypatch, coherent)
    original = json.loads(config.read_text())
    original.update(nominal)
    config.write_bytes(b"\xef\xbb\xbf" + json.dumps(original, indent=3).encode())
    raw = config.read_bytes()
    diagnostic = diagnose(config)
    assert diagnostic["status"] == "attention"
    assert str(tmp_path) not in json.dumps(diagnostic)
    overrides = {} if coherent else {"vault_path": brain.vault, "state_path": brain.state}
    if not coherent:
        assert {r["code"] for r in diagnostic["roots"].values()} == {"inconsistent-resolution"}
        assert repair(config)["status"] == "blocked"
        with pytest.raises(ValueError, match="Path escapes root"):
            type(brain)(load_config(config))
    preview = repair(config, overrides)
    assert preview["status"] == "ready", preview
    assert config.read_bytes() == raw and snapshot(brain) == before
    assert not list(config.parent.glob("selected.json.paths*"))
    applied = repair(config, overrides, True, preview["configuration_revision"])
    assert applied["status"] == "repaired", applied
    assert Path(applied["backup"]).read_bytes() == raw
    assert applied["restart_required"]
    current = json.loads(config.read_text())
    assert current["custom"] == original["custom"]
    assert Path(current["vault_path"]) == brain.vault and Path(current["state_path"]) == brain.state
    assert snapshot(brain) == before
    assert (
        Catalog(type(brain)(load_config(config))).snapshot("note")["items"][0]["id"]
        == "note:personal:git-version"
    )
    assert repair(config)["status"] == "no-change"


def test_wrong_or_empty_store_and_changed_config_refused(brain, tmp_path):
    config = deployment(brain, tmp_path)
    raw = config.read_bytes()
    other = tmp_path / "other"
    other.mkdir()
    result = repair(config, {"vault_path": other}, True)
    assert result == {"status": "blocked", "reason": "different-vault-store"}
    assert config.read_bytes() == raw and list(other.iterdir()) == []
    preview = repair(config)
    config.write_text(json.dumps({**json.loads(raw), "custom": {"changed": True}}))
    assert repair(config, apply=True, expected_revision=preview["configuration_revision"]) == {
        "status": "blocked",
        "reason": "configuration-changed",
    }
    assert repair(config, {"custom": "overwrite"})["reason"] == "invalid-override"


def test_missing_roots_and_unavailable_configuration_do_not_initialize(tmp_path, monkeypatch):
    config = tmp_path / "selected.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "personal",
                "timezone": "Europe/Madrid",
                "vault_path": str(tmp_path / "absent-vault"),
                "state_path": str(tmp_path / "absent-state"),
            }
        )
    )
    assert diagnose(config)["status"] == "attention"
    assert repair(config, apply=True)["reason"] == "missing-root"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["selected.json"]
    original = Path.open

    def denied(path, *args, **kwargs):
        if path == config:
            raise PermissionError("private-path-must-not-leak")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    assert "private-path" not in json.dumps(diagnose(config))
    assert repair(config) == {"status": "blocked", "reason": "unavailable"}


def test_failed_apply_keeps_config_and_exact_recovery_copy(brain, tmp_path, monkeypatch):
    import second_brain.paths as paths

    config = deployment(brain, tmp_path)
    nominal = virtualize(brain, tmp_path, monkeypatch, True)
    config.write_text(json.dumps({**json.loads(config.read_text()), **nominal}))
    raw = config.read_bytes()

    def failed(*args):
        raise OSError("private-write-path")

    monkeypatch.setattr(paths, "atomic_write", failed)
    assert repair(config, apply=True) == {"status": "blocked", "reason": "unavailable"}
    assert config.read_bytes() == raw
    backups = list(config.parent.glob("selected.json.paths-before-*.json"))
    assert len(backups) == 1 and backups[0].read_bytes() == raw


def test_recanonicalization_does_not_accept_child_escape_or_linked_roots(tmp_path, monkeypatch):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    original = Path.resolve

    def escaped(path, *args, **kwargs):
        return (
            original(outside / path.name)
            if path == root / "escape"
            else original(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "resolve", escaped)
    for relative in ["../outside", outside, "escape"]:
        with pytest.raises(ValueError):
            scoped_path(root, relative)
    junction = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path == root or junction(path))
    with pytest.raises(ValueError, match="Linked"):
        scoped_path(root, "anything")


def test_new_initializer_persists_post_creation_physical_state_and_selected_name(
    tmp_path, monkeypatch, capsys
):
    import runpy
    import sys
    import subprocess
    from types import SimpleNamespace
    import fastmcp

    script = Path(__file__).resolve().parents[1] / "scripts/init-personal.py"
    nominal, physical = tmp_path / "virtual-local", tmp_path / "physical-local"
    original_resolve, original_mkdir = Path.resolve, Path.mkdir

    def resolved(path, *args, **kwargs):
        if path == script:
            return tmp_path / "sources/memory/scripts/init-personal.py"
        if path == nominal and physical.exists():
            return physical
        return original_resolve(path, *args, **kwargs)

    def mkdir(path, *args, **kwargs):
        return original_mkdir(physical if path == nominal else path, *args, **kwargs)

    class Provider:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def call_tool(self, *args):
            return SimpleNamespace(
                is_error=False, data={"projects": [{"name": "second-brain-personal"}]}
            )

    monkeypatch.setattr(Path, "resolve", resolved)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(fastmcp, "Client", Provider)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(sys, "argv", [str(script), "--config", str(nominal / "chosen-name.json")])
    runpy.run_path(str(script), run_name="__main__")
    output = json.loads(capsys.readouterr().out)
    assert Path(output["config_path"]) == physical / "chosen-name.json"
    saved = json.loads((physical / "chosen-name.json").read_text())
    assert Path(saved["state_path"]) == physical
    assert Path(saved["basic_memory_config_dir"]) == physical / "basic-memory"
    assert (tmp_path / "SecondBrain-Personal").is_dir()
    assert not nominal.exists()


@pytest.mark.parametrize("legacy", [False, True], ids=["current-config", "legacy-bom-config"])
def test_explicit_config_is_shared_by_powershell_cli_mcp_and_http(
    brain, tmp_path, monkeypatch, legacy
):
    import asyncio
    import shutil
    import subprocess
    import sys
    import threading
    from urllib.request import urlopen
    from urllib.parse import urlencode
    from fastmcp import Client
    from second_brain.viewer import ViewerServer

    config = deployment(brain, tmp_path)
    if legacy:
        config = config.with_name("legacy selected config.json")
        config.write_bytes(
            b"\xef\xbb\xbf" + json.dumps({**brain.config, "schema_version": 1}).encode()
        )
    expected = brain.read("git-version")
    before = snapshot(brain)
    config_bytes = config.read_bytes()
    identity = Catalog(brain).snapshot("note")["diagnostics"]["store_id"]
    monkeypatch.setenv("SECOND_BRAIN_CONFIG", str(tmp_path / "wrong-config.json"))
    shell = shutil.which("pwsh") or shutil.which("powershell")
    arguments = [
        sys.executable,
        "-m",
        "second_brain.cli",
        "--config",
        str(config),
        "read",
        "git-version",
    ]
    if shell:
        script = tmp_path / "read-selected.ps1"
        script.write_text(
            "param([string]$PythonPath, [string]$ConfigPath)\n& $PythonPath -m second_brain.cli --config $ConfigPath read 'git-version'\nexit $LASTEXITCODE\n"
        )
        arguments = [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            "-PythonPath",
            sys.executable,
            "-ConfigPath",
            str(config),
        ]
    process = subprocess.run(
        arguments, cwd=tmp_path, capture_output=True, encoding="utf-8", timeout=20
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == expected
    base = [sys.executable, "-m", "second_brain.cli", "--config", str(config)]
    for args in [["catalog", "--kind", "note"], ["doctor", "--catalog"]]:
        check = subprocess.run(base + args, capture_output=True, encoding="utf-8", timeout=15)
        assert check.returncode == 0, check.stderr
        data = json.loads(check.stdout)
        diagnostics = data.get("diagnostics", data.get("catalog"))
        assert diagnostics["store_id"] == identity
        assert diagnostics["registered_notes"] == diagnostics["readable_notes"] == 1

    async def stdio():
        transport = {
            "mcpServers": {
                "brain": {
                    "command": sys.executable,
                    "args": ["-m", "second_brain.cli", "--config", str(config), "serve"],
                    "env": {
                        "FASTMCP_CHECK_FOR_UPDATES": "off",
                        "FASTMCP_SHOW_SERVER_BANNER": "false",
                    },
                }
            }
        }
        async with Client(transport) as client:
            read = await client.call_tool("read_memory", {"note_id": "git-version"})
            assert not read.is_error and read.data == expected
            catalog = await client.call_tool("list_content", {"kind": "note"})
            assert [r["id"] for r in catalog.data["items"]] == ["note:personal:git-version"]
            assert catalog.data["diagnostics"]["store_id"] == identity

    asyncio.run(asyncio.wait_for(stdio(), timeout=30))
    with ViewerServer(type(brain)(load_config(config)), 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(server.url + "api/items?kind=note", timeout=5) as response:
                result = json.loads(response.read())
                assert result["items"][0]["id"] == "note:personal:git-version"
                assert result["diagnostics"]["store_id"] == identity
            with urlopen(
                server.url + "api/content?" + urlencode({"id": "note:personal:git-version"}),
                timeout=5,
            ) as response:
                assert "git --version" in json.loads(response.read())["text"]
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert snapshot(brain) == before
    assert config.read_bytes() == config_bytes
    assert not (tmp_path / "wrong-config.json").exists()


def test_initializer_preserves_existing_explicit_config_without_bootstrap(brain, tmp_path):
    import subprocess
    import sys

    config = deployment(brain, tmp_path)
    before = snapshot(brain)
    raw = config.read_bytes()
    script = Path(__file__).resolve().parents[1] / "scripts/init-personal.py"
    result = subprocess.run(
        [sys.executable, str(script), "--config", str(config)],
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "preserved",
        "config_path": str(config.resolve()),
    }
    assert config.read_bytes() == raw and snapshot(brain) == before


def test_unavailable_existing_deployment_cannot_initialize_empty_replacement(brain, tmp_path):
    from second_brain.core import Brain

    brain.capture(event())
    original = snapshot(brain)
    absent_vault, absent_state = tmp_path / "absent-vault", tmp_path / "absent-state"
    with pytest.raises(ValueError, match="vault is unavailable"):
        Brain({**brain.config, "vault_path": str(absent_vault)})
    with pytest.raises(ValueError, match="requires its ledger"):
        Brain({**brain.config, "state_path": str(absent_state)})
    assert not absent_vault.exists() and not absent_state.exists()
    assert snapshot(brain) == original


def test_path_cli_preview_apply_and_diagnostics_use_selected_config(
    brain, tmp_path, monkeypatch, capsys
):
    import sys
    from second_brain.cli import main

    config = deployment(brain, tmp_path)
    nominal = virtualize(brain, tmp_path, monkeypatch, True)
    config.write_text(json.dumps({**json.loads(config.read_text()), **nominal}))
    monkeypatch.setenv("SECOND_BRAIN_CONFIG", str(tmp_path / "wrong.json"))

    def invoke(command):
        monkeypatch.setattr(sys, "argv", ["second-brain", "--config", str(config), *command])
        try:
            main()
        except SystemExit as error:
            status = error.code
        else:
            status = 0
        captured = capsys.readouterr()
        assert captured.err == ""
        return status, json.loads(captured.out)

    code, diagnostic = invoke(["paths"])
    assert code == 1 and diagnostic["status"] == "attention"
    assert str(tmp_path) not in json.dumps(diagnostic)
    code, preview = invoke(["repair-paths"])
    assert code == 0 and preview["status"] == "ready"
    code, applied = invoke(
        ["repair-paths", "--apply", "--expect-revision", preview["configuration_revision"]]
    )
    assert code == 0 and applied["status"] == "repaired"
    assert invoke(["paths"])[0] == 0
    assert not (tmp_path / "wrong.json").exists()


def test_powershell_hardening_rejects_broad_root_before_acl_writes(tmp_path):
    import os
    import shutil
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows ACL entrypoint")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    config = tmp_path / "unsafe-root.json"
    config.write_text(
        json.dumps(
            {"scope": "personal", "vault_path": tmp_path.anchor, "state_path": str(tmp_path)}
        )
    )
    secure = Path(__file__).resolve().parents[1] / "scripts/secure-personal.ps1"
    wrapper = tmp_path / "guarded-hardening.ps1"
    wrapper.write_text(
        "param([string]$ScriptPath, [string]$ConfigPath)\nfunction Set-Acl { throw 'unsafe-ACL-invocation' }\nfunction Get-Acl { [pscustomobject]@{ Sddl = 'synthetic' } }\n& $ScriptPath -ConfigPath $ConfigPath\n"
    )
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(wrapper),
            "-ScriptPath",
            str(secure),
            "-ConfigPath",
            str(config),
        ],
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode != 0 and "private directories" in result.stderr
    assert "unsafe-ACL-invocation" not in result.stderr
    assert not (tmp_path / "acl-before.json").exists()


def test_initializer_probe_handles_stable_root_with_redirected_new_children(tmp_path, monkeypatch):
    import tempfile
    from second_brain.core import initialize_root

    nominal, physical = tmp_path / "nominal", tmp_path / "physical"
    nominal.mkdir()
    physical.mkdir()
    resolve, stat, unlink, mkstemp = Path.resolve, Path.stat, Path.unlink, tempfile.mkstemp

    def redirected(path, *args, **kwargs):
        if path.is_relative_to(nominal) and path != nominal:
            return resolve(physical / path.relative_to(nominal), *args, **kwargs)
        return resolve(path, *args, **kwargs)

    def redirected_stat(path, *args, **kwargs):
        return stat(
            physical / path.relative_to(nominal)
            if path.is_relative_to(nominal) and path != nominal
            else path,
            *args,
            **kwargs,
        )

    def created(*args, **kwargs):
        assert kwargs["dir"] == nominal
        kwargs["dir"] = physical
        fd, filename = mkstemp(*args, **kwargs)
        return fd, str(nominal / Path(filename).name)

    def removed(path, *args, **kwargs):
        return unlink(physical / path.relative_to(nominal), *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(Path, "stat", redirected_stat)
    monkeypatch.setattr(Path, "unlink", removed)
    monkeypatch.setattr(tempfile, "mkstemp", created)
    assert initialize_root(nominal) == physical
    assert list(physical.iterdir()) == [] and list(nominal.iterdir()) == []


def test_installer_and_upgrade_refuse_incoherent_roots_before_host_writes(
    brain, tmp_path, monkeypatch
):
    from second_brain.install import install, upgrade

    config = deployment(brain, tmp_path)
    nominal = virtualize(brain, tmp_path, monkeypatch, False)
    config.write_text(json.dumps({**json.loads(config.read_text()), **nominal}))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    before = snapshot(brain)
    for operation in [install, upgrade]:
        with pytest.raises(ValueError, match="explicit repair"):
            operation(config)
    assert not (tmp_path / ".codex").exists() and snapshot(brain) == before


def test_reviewed_physical_roots_do_not_select_another_host_namespace(brain, tmp_path, monkeypatch):
    from second_brain.core import Brain

    config = deployment(brain, tmp_path)
    nominal = virtualize(brain, tmp_path, monkeypatch, True)
    config.write_text(json.dumps({**json.loads(config.read_text()), **nominal}))
    preview = repair(config)
    assert preview["status"] == "ready"
    reviewed = preview["proposed_roots"]
    other = Brain(
        {
            **brain.config,
            "vault_path": str(tmp_path / "other-vault"),
            "state_path": str(tmp_path / "other-state"),
        }
    )
    other.capture(event(body="A different synthetic host namespace."))
    before, other_before, raw = snapshot(brain), snapshot(other), config.read_bytes()
    virtualize(other, tmp_path, monkeypatch, True)
    blocked = repair(config, reviewed, True, preview["configuration_revision"])
    assert blocked == {"status": "blocked", "reason": "different-state-store"}
    assert (
        config.read_bytes() == raw and snapshot(brain) == before and snapshot(other) == other_before
    )
