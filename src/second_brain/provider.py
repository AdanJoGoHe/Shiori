"""Local Basic Memory adapter; canonical note validation stays in the core."""

import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client


class ProviderUnavailable(RuntimeError):
    """A controlled diagnostic code, without provider output or private paths."""


def project_name(config):
    scope = config.get("scope", "personal")
    if scope not in {"personal", "work"}:
        raise ProviderUnavailable("invalid-configuration")
    return f"second-brain-{scope}"


def executable():
    return Path(sys.executable).with_name("basic-memory.exe" if os.name == "nt" else "basic-memory")


def environment(config):
    return {
        "BASIC_MEMORY_CONFIG_DIR": config["basic_memory_config_dir"],
        "BASIC_MEMORY_HOME": config["vault_path"],
        "BASIC_MEMORY_CLOUD_MODE": "false",
        "BASIC_MEMORY_SEMANTIC_SEARCH_ENABLED": "false",
        "BASIC_MEMORY_LOGFIRE_ENABLED": "false",
        "BASIC_MEMORY_AUTO_UPDATE": "false",
        "DO_NOT_TRACK": "1",
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "FASTMCP_SHOW_SERVER_BANNER": "false",
        "FASTMCP_TELEMETRY_MODE": "off",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }


def process_environment(config):
    return {
        **{key: value for key, value in os.environ.items() if not key.startswith("BASIC_MEMORY_")},
        **environment(config),
    }


def validate_config(config):
    if not config.get("basic_memory_config_dir"):
        raise ProviderUnavailable("not-configured")
    try:
        settings = Path(config["basic_memory_config_dir"]) / "config.json"
        if settings.stat().st_size > 100000:
            raise ValueError("Oversized provider configuration")
        projects = json.loads(settings.read_text(encoding="utf-8-sig"))["projects"]
        entry = projects[project_name(config)]
        if (
            set(projects) != {project_name(config)}
            or entry.get("mode", "local") != "local"
            or Path(entry["path"]).resolve() != Path(config["vault_path"]).resolve()
        ):
            raise ValueError("Provider project must match the isolated local vault")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ProviderUnavailable("invalid-configuration") from None


async def probe_provider(config):
    """Explicit project-status probe; no reindex, raw output or note bodies returned."""
    process = None
    try:
        validate_config(config)
        process = await asyncio.create_subprocess_exec(
            str(executable()),
            "status",
            "--project",
            project_name(config),
            "--json",
            "--local",
            env=process_environment(config),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(20):
            try:
                await process.stdout.readexactly(1024 * 1024 + 1)
            except asyncio.IncompleteReadError as end:
                raw = end.partial
            else:
                raise ProviderUnavailable("invalid-response")
            await process.wait()
        if process.returncode:
            raise ProviderUnavailable("status-failed")
        try:
            payload = json.loads(raw)
            count, rows = payload["total_files"], payload["observed_files"]
            if (
                type(count) is not int
                or count < 0
                or not isinstance(rows, list)
                or len(rows) != count
            ):
                raise ValueError("Invalid project status")
            if any(
                not isinstance(row, dict) or not isinstance(row.get("path"), str) for row in rows
            ):
                raise ValueError("Invalid observed file")
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ProviderUnavailable("invalid-response") from None
        return {"status": "available", "check": "project-status", "total_files": count}
    except (ProviderUnavailable, OSError, TimeoutError) as error:
        if isinstance(error, ProviderUnavailable):
            reason = str(error)
        elif isinstance(error, FileNotFoundError):
            reason = "executable-not-found"
        elif isinstance(error, TimeoutError):
            reason = "timeout"
        else:
            reason = "provider-error"
        return {"status": "unavailable", "check": "project-status", "reason": reason}
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()


async def provider_search(config, query):
    validate_config(config)
    command = str(executable())
    env = environment(config)
    # External Markdown writes need explicit full-text reindexing in BM 0.23.2.
    process = await asyncio.create_subprocess_exec(
        command,
        "reindex",
        "--search",
        "--project",
        project_name(config),
        env=process_environment(config),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
        if process.returncode:
            raise ProviderUnavailable("reindex-failed")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    # shortcut: one provider process per search; reuse a session if startup latency matters.
    transport = {
        "mcpServers": {
            "memory": {
                "command": command,
                "args": ["mcp", "--project", project_name(config)],
                "env": env,
            }
        }
    }
    async with Client(transport) as client:
        result = await client.call_tool(
            "search_notes",
            {
                "query": query,
                "project": project_name(config),
                "page_size": 5,
                "search_type": "text",
                "output_format": "json",
            },
        )
        if result.is_error:
            raise ProviderUnavailable("search-failed")
        try:
            payload = json.loads(next(b.text for b in result.content if hasattr(b, "text")))
            rows = payload["results"]
            if (
                not isinstance(rows, list)
                or len(rows) > 5
                or any(
                    not isinstance(row, dict) or not isinstance(row.get("file_path"), str)
                    for row in rows
                )
            ):
                raise ValueError("Invalid search result shape")
        except (ValueError, TypeError, KeyError, StopIteration):
            raise ProviderUnavailable("invalid-response") from None
        return rows
