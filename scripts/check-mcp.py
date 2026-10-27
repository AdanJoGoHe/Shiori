"""Real local MCP protocol smoke test; no host integration claims."""

import asyncio
import json
import sys

from fastmcp import Client

from second_brain.cli import default_config
from second_brain.provider import executable, environment as provider_environment
from second_brain.core import Brain


async def main():
    config = json.loads(default_config().read_text())
    brain = Brain(config)
    candidate = {
        "scope": "personal",
        "id": "git-version",
        "event_id": "codex-20261011-git-smoke",
        "title": "Comprobar la versión de Git en PowerShell",
        "type": "command",
        "status": "verified",
        "source_agent": "codex",
        "body": "Ejecutar `git --version` en PowerShell. Requiere Git en PATH. Es una consulta de solo lectura.",
        "evidence": "Ejecutado en este equipo el 2026-10-11: git version 2.55.0.windows.5.",
        "summary": "Verificada la instalación local de Git al preparar Second Brain.",
    }
    print("CLI capture:", brain.capture(candidate))
    environment = provider_environment(config)
    bm = {
        "mcpServers": {
            "memory": {
                "command": str(executable()),
                "args": ["mcp", "--project", "second-brain-personal"],
                "env": environment,
            }
        }
    }
    async with Client(bm) as client:
        projects = await client.call_tool("list_memory_projects", {"output_format": "json"})
        assert "second-brain-personal" in str(projects.data)
        print("Scoped projects:", str(projects.data)[:1000])
        result = await client.call_tool(
            "search_notes", {"query": "git", "project": "second-brain-personal"}
        )
        assert not result.is_error and "git-version" in str(result.data)
        print("Basic Memory search:", str(result.data)[:2000])
        read = await client.call_tool(
            "read_note",
            {
                "identifier": "commands/git-version",
                "project": "second-brain-personal",
                "output_format": "json",
                "include_frontmatter": True,
            },
        )
        assert not read.is_error and "2.55.0" in str(read.data)
        print("Basic Memory read: passed")
    core = {
        "mcpServers": {
            "brain": {
                "command": sys.executable,
                "args": ["-m", "second_brain.cli", "serve"],
                "env": environment,
            }
        }
    }
    async with Client(core) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == {
            "get_context",
            "classify_memory",
            "list_pending_captures",
            "search_memory",
            "read_memory",
            "capture_memory",
            "memory_status",
            "list_content",
            "read_journal",
        }
        status = await client.call_tool("memory_status", {})
        print("Core status:", str(status)[:1000])
        result = await client.call_tool("search_memory", {"query": "git"})
        assert result.data["provider"] == "basic-memory"
        assert result.data["notes"][0]["id"] == "git-version"
        print("Core indexed search: passed")
        duplicate = await client.call_tool("capture_memory", {"candidate": candidate})
        assert duplicate.data["status"] == "duplicate"
        rejected = await client.call_tool(
            "capture_memory", {"candidate": dict(candidate, scope="work")}
        )
        assert rejected.data["status"] == "failed"
        print("Core MCP rejected work scope: passed")
    assert "scope: personal" in brain.read("git-version")
    print("PASS: MCP search/read/deduplication and frontmatter persistence")


asyncio.run(main())
