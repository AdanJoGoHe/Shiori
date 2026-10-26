"""Create an isolated personal deployment. Existing configurations are preserved."""

import json
import os
import argparse
import asyncio
import subprocess
from pathlib import Path

from second_brain.provider import executable, process_environment
from second_brain.core import Brain, atomic_write, canonical_root, initialize_root, load_config
from second_brain.cli import default_config
from second_brain.paths import diagnose
from fastmcp import Client

repo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", type=Path, default=default_config())
config_file = parser.parse_args().config.absolute()
state = config_file.parent
config_name = config_file.name
vault = repo.parent.parent / "SecondBrain-Personal"
if config_file.exists():
    load_config(config_file)
    report = diagnose(config_file)
    if any(
        report.get("roots", {}).get(field, {}).get("code") != "ok"
        for field in ["vault_path", "state_path"]
    ):
        raise ValueError("Existing deployment requires paths/repair-paths before installation")
    print(json.dumps({"status": "preserved", "config_path": str(config_file.resolve())}))
    raise SystemExit(0)
vault = canonical_root(vault)
state = canonical_root(state)
for root in [vault, state]:
    broad = {Path(root.anchor), Path.home().resolve()}
    if os.environ.get("LOCALAPPDATA"):
        broad.add(Path(os.environ["LOCALAPPDATA"]).resolve())
    if root in broad or root.is_relative_to(repo) or repo.is_relative_to(root):
        raise ValueError(
            "Deployment roots must be private directories outside the source repository"
        )
if (state / "ledger.json").exists():
    raise ValueError("Existing memory state requires its original configuration")
brain = Brain(
    {
        "scope": "personal",
        "vault_path": str(vault),
        "state_path": str(state),
        "timezone": "Europe/Madrid",
    }
)
# Probe the namespace even for an existing empty directory before persisting a new config.
vault = initialize_root(brain.vault)
state = initialize_root(brain.state)
config_file = state / config_name
for folder in [
    "profile",
    "projects",
    "knowledge",
    "commands",
    "troubleshooting",
    "decisions",
    "lessons-learned",
    "journal",
    "inbox",
]:
    (vault / folder).mkdir(exist_ok=True)
if not (vault / ".gitignore").exists():
    atomic_write(vault / ".gitignore", ".obsidian/\n*.tmp\n*.lock\n")
if not (vault / "README.md").exists():
    atomic_write(
        vault / "README.md",
        "# Personal Brain\n\nPersonal curated notes. No cloud sync or corporate material.\n",
    )
config = {
    "schema_version": 1,
    "scope": "personal",
    "vault_path": str(vault),
    "state_path": str(state),
    "timezone": "Europe/Madrid",
    "basic_memory_config_dir": str(state / "basic-memory"),
}
atomic_write(config_file, json.dumps(config, indent=2))
bm_dir = state / "basic-memory"
bm_dir.mkdir(exist_ok=True)
bm_config = {
    "projects": {"second-brain-personal": {"path": str(vault), "mode": "local"}},
    "default_project": "second-brain-personal",
    "semantic_search_enabled": False,
    "logfire_enabled": False,
    "logfire_send_to_logfire": False,
    "auto_update": False,
}
atomic_write(bm_dir / "config.json", json.dumps(bm_config, indent=2))
environment = process_environment(config)


async def register_project():
    client_config = {
        "mcpServers": {
            "memory": {
                "command": str(executable()),
                "args": ["mcp", "--project", "second-brain-personal"],
                "env": environment,
            }
        }
    }
    async with Client(client_config) as client:
        result = await client.call_tool("list_memory_projects", {"output_format": "json"})
        if result.is_error or {p["name"] for p in result.data["projects"]} != {
            "second-brain-personal"
        }:
            raise ValueError("Personal project isolation could not be verified")


asyncio.run(asyncio.wait_for(register_project(), timeout=30))
if not (vault / ".git").exists():
    subprocess.run(
        ["git", "init", "-b", "main", str(vault)], check=True, timeout=15, stdout=subprocess.DEVNULL
    )
print(json.dumps({"status": "created", "config_path": str(config_file.resolve())}))
