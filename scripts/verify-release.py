"""Run with the wheel's interpreter, outside a checkout; synthetic data only."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import tomllib
from importlib.resources import files
from importlib.metadata import version
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastmcp import Client

from second_brain.core import Brain
from second_brain.provider import executable, environment as provider_environment
from second_brain.viewer import ViewerServer


def main():
    import second_brain

    assert Path(second_brain.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (
        "Use the installed wheel interpreter"
    )
    root = Path(tempfile.mkdtemp(prefix="second-brain-alpha-"))
    home = root / "home"
    codex = home / ".codex"
    codex.mkdir(parents=True)
    originals = {
        "config.toml": b'[mcp_servers.other]\ncommand = "other"\n',
        "AGENTS.md": b"Keep this instruction\n",
    }
    for name, content in originals.items():
        (codex / name).write_bytes(content)
    config = {
        "schema_version": 1,
        "scope": "personal",
        "timezone": "Europe/Madrid",
        "vault_path": str(root / "vault"),
        "state_path": str(root / "state"),
        "basic_memory_config_dir": str(root / "provider"),
    }
    config_file = root / "config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    environment = dict(
        {key: value for key, value in os.environ.items() if not key.startswith("BASIC_MEMORY_")},
        HOME=str(home),
        USERPROFILE=str(home),
        PYTHONPATH="",
    )
    environment.pop("SECOND_BRAIN_CONFIG", None)

    def cli(*arguments, config_path=config_file):
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "second_brain.cli",
                "--config",
                str(config_path),
                *map(str, arguments),
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
        )
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout)

    for name in ["shiori", "second-brain"]:
        launcher = Path(sys.executable).parent / (name + ".exe" if os.name == "nt" else name)
        process = subprocess.run(
            [str(launcher), "--config", str(config_file), "status"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout) == cli("status")
    assert files("second_brain").joinpath("resources/second-brain/SKILL.md").is_file()
    assert cli("install-codex")["status"] == "installed"
    bound = tomllib.loads((codex / "config.toml").read_text(encoding="utf-8"))["mcp_servers"][
        "second_brain_personal"
    ]
    assert bound["command"] == str(Path(sys.executable).absolute()).replace("\\", "/")
    skill = (codex / "skills/second-brain/SKILL.md").read_text(encoding="utf-8")
    assert (
        "get_context" in skill and "classify_memory" in skill and "list_pending_captures" in skill
    )
    assert "D:\\repo\\memory" not in skill
    # Model an older owned skill; this is compatibility validation, not a released-version upgrade.
    manifest_path = Path(config["state_path"]) / "install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_path = codex / "skills/second-brain/SKILL.md"
    previous_skill = b"# Synthetic previous owned skill\n"
    skill_path.write_bytes(previous_skill)
    manifest["skill_hash"] = hashlib.sha256(previous_skill).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    previous_manifest = manifest_path.read_bytes()
    assert cli("upgrade-codex")["status"] == "upgrade available"
    assert manifest_path.read_bytes() == previous_manifest
    assert skill_path.read_bytes() == previous_skill
    upgraded = cli("upgrade-codex", "--apply")
    assert upgraded["status"] == "upgraded" and upgraded["restart_required"]
    assert skill_path.read_text(encoding="utf-8") == skill
    assert (Path(upgraded["recovery"]) / "SKILL.md").read_bytes() == previous_skill
    assert cli("upgrade-codex", "--apply")["status"] == "up to date"
    assert cli("uninstall")["status"] == "uninstalled"
    assert all((codex / name).read_bytes() == value for name, value in originals.items())
    candidate = {
        "scope": "personal",
        "id": "release-fixture",
        "event_id": "release-fixture-event",
        "type": "lesson",
        "status": "verified",
        "source_agent": "codex",
        "title": "Synthetic Unicode 🧠",
        "body": "Synthetic observation; notes are inert data.",
        "evidence": "Synthetic package acceptance test.",
        "project": "release-test",
    }
    event = root / "event.json"
    event.write_text(json.dumps(candidate), encoding="utf-8")
    assert cli("capture", "--event-file", event)["status"] == "saved"
    assert cli("capture", "--event-file", event)["status"] == "duplicate"
    selected_store = cli("catalog", "--kind", "note")["diagnostics"]["store_id"]
    assert (
        cli("context", "synthetic", "--project", "release-test")["notes"][0]["id"]
        == candidate["id"]
    )
    assert cli("pending")["total"] == 0
    assert cli("journal", "--project", "release-test")["total"] == 1
    # Model a persisted lexical alias; repair must preserve the selected store and prior bytes.
    lexical = dict(config)
    for field in ["vault_path", "state_path"]:
        path = Path(config[field])
        lexical[field] = str(path / ".." / path.name)
    config_file.write_text(json.dumps(lexical), encoding="utf-8")
    previous_config = config_file.read_bytes()
    preview = cli("repair-paths")
    assert preview["status"] == "ready"
    assert config_file.read_bytes() == previous_config
    physical_arguments = [
        part
        for field, value in preview["proposed_roots"].items()
        for part in ["--" + field.replace("_", "-"), value]
    ]
    repaired = cli(
        "repair-paths",
        *physical_arguments,
        "--apply",
        "--expect-revision",
        preview["configuration_revision"],
    )
    assert repaired["status"] == "repaired"
    assert Path(repaired["backup"]).read_bytes() == previous_config
    assert cli("repair-paths")["status"] == "no-change"
    provider_dir = Path(config["basic_memory_config_dir"])
    provider_dir.mkdir()
    (provider_dir / "config.json").write_text(
        json.dumps(
            {
                "projects": {
                    "second-brain-personal": {"path": config["vault_path"], "mode": "local"}
                },
                "default_project": "second-brain-personal",
                "semantic_search_enabled": False,
                "logfire_enabled": False,
                "auto_update": False,
            }
        ),
        encoding="utf-8",
    )

    async def mcp():
        async def register_provider():
            setup = {
                "mcpServers": {
                    "memory": {
                        "command": str(executable()),
                        "args": ["mcp", "--project", "second-brain-personal"],
                        "env": {**environment, **provider_environment(config)},
                    }
                }
            }
            async with Client(setup) as client:
                projects = await client.call_tool("list_memory_projects", {"output_format": "json"})
                assert not projects.is_error
                assert {p["name"] for p in projects.data["projects"]} == {"second-brain-personal"}

        # Match installer registration; cold database setup is not a search deadline test.
        await asyncio.wait_for(register_provider(), timeout=45)
        transport = {
            "mcpServers": {
                "brain": {
                    "command": sys.executable,
                    "args": ["-m", "second_brain.cli", "--config", str(config_file), "serve"],
                    "env": {
                        "PYTHONPATH": "",
                        "FASTMCP_CHECK_FOR_UPDATES": "off",
                        "FASTMCP_SHOW_SERVER_BANNER": "false",
                    },
                }
            }
        }
        async with Client(transport) as client:
            names = {tool.name for tool in await client.list_tools()}
            assert names == {
                "search_memory",
                "read_memory",
                "capture_memory",
                "memory_status",
                "get_context",
                "classify_memory",
                "list_pending_captures",
                "list_content",
                "read_journal",
            }
            diary = await client.call_tool("read_journal", {"project": "release-test"})
            assert diary.data["scope"] == "personal" and diary.data["total"] >= 1
            observation = await client.call_tool("memory_status", {})
            assert observation.data["index"]["status"] == "not-checked"
            active = await client.call_tool("memory_status", {"check_provider": True})
            assert active.data["provider_check"]["status"] == "available", active.data
            assert active.data["provider_check"]["total_files"] >= 1
            assert active.data["index"]["status"] == "not-checked"
            indexed = await client.call_tool("search_memory", {"query": "Synthetic"})
            assert indexed.data["provider"] == "basic-memory", indexed.data
            assert indexed.data["notes"][0]["id"] == candidate["id"]
            observation = await client.call_tool("memory_status", {})
            assert observation.data["index"] == {"status": "available", "reason": None}
            result = await client.call_tool(
                "get_context", {"query": "synthetic", "max_chars": 2000}
            )
            assert result.data["notes"][0]["id"] == candidate["id"]
            for denied in [
                dict(candidate, scope="work"),
                dict(candidate, body="password=synthetic-secret"),
            ]:
                result = await client.call_tool("capture_memory", {"candidate": denied})
                assert result.data["status"] == "failed"
            result = await client.call_tool("read_memory", {"note_id": candidate["id"]})
            assert "Synthetic observation" in result.data
            result = await client.call_tool("memory_status", {})
            assert result.data["scope"] == "personal"
            result = await client.call_tool("list_pending_captures", {})
            assert result.data["total"] == 0
            result = await client.call_tool("list_content", {"kind": "note"})
            assert not result.is_error
            assert result.data["diagnostics"]["store_id"] == selected_store
            assert result.data["diagnostics"]["registered_notes"] == 1
            assert result.data["diagnostics"]["readable_notes"] == 1
            result = await client.call_tool(
                "search_memory",
                {
                    "query": "synthetic",
                    "filters": {"project": "release-test"},
                },
            )
            assert result.data["notes"][0]["id"] == candidate["id"]
            result = await client.call_tool(
                "classify_memory",
                {
                    "candidate": candidate,
                    "assessment": {
                        "material": "personal",
                        "reusable": True,
                        "meaningful": True,
                        "evidence_kind": "observed",
                    },
                },
            )
            assert result.data["decision"] == "skip" and result.data["reason"] == "duplicate-event"

    asyncio.run(mcp())
    assert cli("doctor", "--provider")["provider_check"]["status"] == "available"
    assert cli("paths")["status"] == "ok"
    diagnostic = cli("doctor", "--catalog")
    assert diagnostic["status"] == "ready"
    assert diagnostic["catalog"]["store_id"] == selected_store

    server = ViewerServer(Brain(config), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = server.url
        with urlopen(url, timeout=5) as response:
            assert b"highlights.js" in response.read()
        for name in ("app.js", "style.css", "theme.js", "highlights.js"):
            with urlopen(url + name, timeout=5) as response:
                assert response.status == 200 and response.read()
        document = server.viewer.content("note:personal:release-fixture")
        quote = "Synthetic observation"
        start = document["text"].index(quote)
        server.viewer.save_annotation(
            {
                "document_id": document["item"]["id"],
                "revision": document["revision"],
                "start": start,
                "end": start + len(quote),
                "quote": quote,
                "title": "Remember fixture purpose",
                "description": "Recover a command by intent",
                "color": "green",
                "tags": ["comando"],
            }
        )
        with urlopen(url + "api/items?view=fragments&category=comando", timeout=5) as response:
            fragments = json.loads(response.read())
            assert fragments["diagnostics"]["store_id"] == selected_store
            assert fragments["diagnostics"]["status"] == "ready"
            assert fragments["total"] == 1
            assert fragments["items"][0]["annotation"]["quote"] == quote
            assert fragments["items"][0]["annotation"]["anchor"]["status"] == "resolved"
        with urlopen(url + "api/items?view=fragments&q=purpose%20intent", timeout=5) as response:
            named = json.loads(response.read())
            assert named["total"] == 1
            assert named["items"][0]["annotation"]["title"] == "Remember fixture purpose"
        try:
            urlopen(
                Request(
                    url + "api/annotations",
                    data=b"{}",
                    headers={
                        "Origin": "http://untrusted.invalid",
                        "Content-Type": "application/json",
                    },
                ),
                timeout=5,
            )
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("Cross-origin write accepted")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert cli("pause")["paused"] is True
    assert cli("backup", "--output", root / "backup")["status"] == "backed-up"
    # Recovery does not consult the missing original configuration.
    config_file.rename(root / "original-config.json")
    assert (
        cli("restore", "--input", root / "backup", "--destination", root / "restored")["paused"]
        is True
    )
    recovered = root / "restored/config.json"
    assert cli("doctor", config_path=recovered)["note_validation"] == "passed"
    assert cli("resume", config_path=recovered)["paused"] is False
    assert cli("capture", "--event-file", event, config_path=recovered)["status"] == "duplicate"
    print(
        json.dumps(
            {
                "result": "passed",
                "version": version("second-brain"),
                "checks": [
                    "wheel-skill",
                    "shiori-and-legacy-cli-same-deployment",
                    "install-uninstall-preserves-settings",
                    "owned-upgrade-preview-apply-retry",
                    "cli-capture-context-dedupe",
                    "stdio-nine-tools",
                    "real-basic-memory-indexed-search",
                    "explicit-cli-mcp-provider-status",
                    "scope-secret-denial",
                    "viewer-assets-origin",
                    "marked-fragment-search",
                    "same-store-path-repair",
                    "backup-restore-without-original-config",
                    "paused-recovery-dedupe",
                ],
                "data": "synthetic-only",
            }
        )
    )


if __name__ == "__main__":
    main()
