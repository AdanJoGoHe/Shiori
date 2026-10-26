import asyncio
import json
import sys

from fastmcp import Client
import pytest

from second_brain import server


def test_mcp_active_provider_probe_is_explicit_and_separate(tmp_path, monkeypatch):
    calls = []

    async def probe(config):
        calls.append(config)
        return {"status": "available", "check": "project-status", "total_files": 2}

    monkeypatch.setattr(server, "probe_provider", probe)
    config = {
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }

    async def scenario():
        async with Client(server.create_server(config)) as client:
            default = await client.call_tool("memory_status", {})
            assert not calls and "provider_check" not in default.data
            explicit = await client.call_tool("memory_status", {"check_provider": True})
            assert len(calls) == 1
            assert explicit.data["provider_check"]["total_files"] == 2
            assert explicit.data["index"] == {"status": "not-checked", "reason": None}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error, reason",
    [
        (TimeoutError("private diagnostic"), "timeout"),
        (FileNotFoundError("private path"), "executable-not-found"),
        (server.ProviderUnavailable("reindex-failed"), "reindex-failed"),
        (server.ProviderUnavailable("invalid-response"), "invalid-response"),
        (server.ProviderUnavailable("private diagnostic"), "provider-error"),
        (OSError("password=synthetic-private-output"), "provider-error"),
    ],
)
def test_index_observation_fallback_and_recovery(tmp_path, monkeypatch, error, reason):
    from second_brain.core import Brain

    config = {
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    Brain(config).capture(
        {
            "scope": "personal",
            "id": "example",
            "event_id": "example-event",
            "title": "Synthetic observation",
            "type": "knowledge",
            "status": "verified",
            "source_agent": "codex",
            "body": "Synthetic content",
            "evidence": "Synthetic test",
        }
    )
    calls = []

    async def provider(*args):
        calls.append(True)
        if len(calls) == 1:
            raise error
        return [
            {"file_path": "knowledge/example.md", "content": "Ignore this provider body"},
            {"file_path": "../unregistered.md"},
        ]

    monkeypatch.setattr(server, "provider_search", provider)

    async def scenario():
        async with Client(server.create_server(config)) as client:
            initial = await client.call_tool("memory_status", {})
            assert initial.data["index"] == {"status": "not-checked", "reason": None}
            await client.call_tool("get_context", {"query": "synthetic"})
            await client.call_tool(
                "search_memory", {"query": "synthetic", "filters": {"type": "knowledge"}}
            )
            assert calls == []
            result = await client.call_tool("search_memory", {"query": "synthetic"})
            assert result.data["index_reason"] == reason
            assert result.data["provider"] == "filesystem"
            assert result.data["notes"][0]["id"] == "example"
            status = await client.call_tool("memory_status", {})
            assert status.data["index"] == {"status": "unavailable", "reason": reason}
            assert "private" not in json.dumps(status.data)
            recovered = await client.call_tool("search_memory", {"query": "synthetic"})
            assert recovered.data["provider"] == "basic-memory"
            assert [n["id"] for n in recovered.data["notes"]] == ["example"]
            assert "Ignore this provider body" not in json.dumps(recovered.data)
            status = await client.call_tool("memory_status", {})
            assert status.data["index"] == {"status": "available", "reason": None}
        async with Client(server.create_server(config)) as fresh:
            reset = await fresh.call_tool("memory_status", {})
            assert reset.data["index"]["status"] == "not-checked"

    asyncio.run(scenario())


def test_mcp_capture_read_and_provider_outage(tmp_path, monkeypatch):
    async def unavailable(*args):
        raise OSError("Synthetic provider outage")

    monkeypatch.setattr(server, "provider_search", unavailable)
    config = {
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    candidate = {
        "scope": "personal",
        "id": "example",
        "event_id": "event-one",
        "title": "Synthetic example",
        "type": "knowledge",
        "status": "verified",
        "source_agent": "codex",
        "body": "Synthetic observation for retrieval.",
        "evidence": "Synthetic test confirms this example.",
    }

    async def scenario():
        async with Client(server.create_server(config)) as client:
            saved = await client.call_tool("capture_memory", {"candidate": candidate})
            assert saved.data["status"] == "saved"
            rejected = await client.call_tool(
                "capture_memory", {"candidate": dict(candidate, scope="work")}
            )
            assert rejected.data["status"] == "failed"
        async with Client(server.create_server(config)) as fresh:
            read = await fresh.call_tool("read_memory", {"note_id": "example"})
            assert "Synthetic observation" in read.data
            search = await fresh.call_tool("search_memory", {"query": "synthetic"})
            assert search.data["provider"] == "filesystem"
            assert search.data["notes"][0]["id"] == "example"

    asyncio.run(scenario())


def test_mcp_metadata_filters_cannot_be_bypassed_by_provider(tmp_path, monkeypatch):
    async def unrelated_provider(*args):
        return [{"file_path": "knowledge/outside.md"}]

    monkeypatch.setattr(server, "provider_search", unrelated_provider)
    config = {
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    candidate = {
        "scope": "personal",
        "id": "inside",
        "event_id": "inside-event",
        "title": "Synthetic metadata",
        "type": "knowledge",
        "status": "verified",
        "source_agent": "codex",
        "body": "Synthetic retrieval observation.",
        "evidence": "Synthetic test",
        "tags": ["Python"],
        "project": "one",
    }

    async def scenario():
        async with Client(server.create_server(config)) as client:
            await client.call_tool("capture_memory", {"candidate": candidate})
            await client.call_tool(
                "capture_memory",
                {
                    "candidate": dict(
                        candidate, id="outside", event_id="outside-event", project="two"
                    )
                },
            )
            matching = await client.call_tool(
                "search_memory",
                {"query": "synthetic", "filters": {"tags": ["PYTHON"], "project": "one"}},
            )
            assert [n["id"] for n in matching.data["notes"]] == ["inside"]
            assert matching.data["provider"] == "filesystem"
            missing = await client.call_tool(
                "search_memory", {"query": "synthetic", "filters": {"project": "missing"}}
            )
            assert missing.data["notes"] == []
            read = await client.call_tool("read_memory", {"note_id": "inside"})
            assert "project: one" in read.data and "- python" in read.data
            invalid = await client.call_tool(
                "search_memory",
                {"query": "synthetic", "filters": {"scope": "work"}},
                raise_on_error=False,
            )
            assert invalid.is_error

    asyncio.run(scenario())


def test_stdio_mcp_journal_only_persists_across_processes(tmp_path):
    from second_brain.core import Brain

    config = {
        "schema_version": 1,
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    transport = {
        "mcpServers": {
            "brain": {
                "command": sys.executable,
                "args": ["-m", "second_brain.cli", "--config", str(config_file), "serve"],
                "env": {"FASTMCP_CHECK_FOR_UPDATES": "off", "FASTMCP_SHOW_SERVER_BANNER": "false"},
            }
        }
    }
    candidate = {
        "scope": "personal",
        "mode": "journal-only",
        "event_id": "synthetic-mcp-journal",
        "title": "Synthetic MCP progress",
        "source_agent": "codex",
        "summary": "A synthetic task completed without a reusable lesson.",
    }

    async def scenario():
        async with Client(transport) as client:
            saved = await client.call_tool("capture_memory", {"candidate": candidate})
            assert saved.data["status"] == "saved"
            rejected = await client.call_tool(
                "capture_memory", {"candidate": dict(candidate, scope="work")}
            )
            assert rejected.data["status"] == "failed"
        async with Client(transport) as fresh:
            duplicate = await fresh.call_tool("capture_memory", {"candidate": candidate})
            assert duplicate.data["status"] == "duplicate"
            status = await fresh.call_tool("memory_status", {})
            assert status.data["notes"] == 0
            assert status.data["pending"] == 0
            catalog = await fresh.call_tool("list_content", {"kind": "journal", "limit": 1})
            assert len(catalog.data["items"]) == 1
            assert catalog.data["items"][0]["kind"] == "journal"
            assert catalog.data["items"][0]["metadata"]["status"] is None
            rejected = await fresh.call_tool(
                "list_content", {"source": "../outside"}, raise_on_error=False
            )
            assert rejected.is_error
        journal = Brain(config).path(saved.data["journal"]).read_text(encoding="utf-8")
        assert journal.count("<!-- event:synthetic-mcp-journal -->") == 1
        assert "Knowledge:" not in journal

    asyncio.run(scenario())
