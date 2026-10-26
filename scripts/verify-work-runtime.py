"""Installed-wheel and optional two-version work-runtime check; synthetic data only."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from fastmcp import Client

from second_brain.core import Brain, load_config
from second_brain.runtime import python_in


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--next-release-dir", type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    temporary = Path(tempfile.mkdtemp(prefix="shiori-work-check-"))
    root = temporary / "Synthetic café work"
    if os.name == "nt":
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(release / "install-shiori.ps1"),
            "-ReleaseDir",
            str(release),
            "-InstallDir",
            str(root),
        ]
        preview = subprocess.run(command, capture_output=True, timeout=30)
        assert preview.returncode == 0 and not root.exists(), preview.stderr.decode(
            errors="replace"
        )
        applied = subprocess.run([*command, "-Apply"], capture_output=True, timeout=600)
        assert applied.returncode == 0, applied.stderr.decode(errors="replace")
    else:
        from second_brain.runtime import install

        install(root, release, apply=True)

    def cli(*arguments):
        result = subprocess.run(
            [sys._base_executable, "-I", str(root / "shiori.py"), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    status = cli("status")
    first = status["active"]
    assert status["memory"]["scope"] == "work"
    executable = python_in(root, first)
    check = subprocess.run(
        [
            str(executable),
            "-I",
            "-c",
            "import second_brain,sys; from pathlib import Path; "
            "assert Path(second_brain.__file__).is_relative_to(Path(sys.prefix))",
        ],
        capture_output=True,
        timeout=15,
    )
    assert check.returncode == 0, check.stderr
    skills = temporary / "synthetic-home/.augment/skills"
    assert cli("augment", "--skills-dir", str(skills))["applied"] is False
    assert not skills.exists()
    assert cli("augment", "--skills-dir", str(skills), "--apply")["applied"]

    candidate = {
        "scope": "work",
        "id": "synthetic-git-command",
        "event_id": "synthetic-event",
        "title": "Synthetic Git version check",
        "type": "command",
        "status": "verified",
        "source_agent": "augment-jetbrains",
        "body": "Run git --version; synthetic fixture.",
        "evidence": "Synthetic protocol fixture, not an actual company command.",
        "tags": ["command"],
        "project": "synthetic",
    }

    async def stdio():
        transport = {
            "mcpServers": {
                "shiori_work": {
                    "command": sys._base_executable,
                    "args": ["-I", str(root / "shiori.py"), "run", "serve"],
                }
            }
        }
        async with Client(transport) as client:
            assert len(await client.list_tools()) == 8
            result = await client.call_tool("memory_status", {})
            assert result.data["scope"] == "work"
            result = await client.call_tool(
                "classify_memory",
                {
                    "candidate": candidate,
                    "assessment": {
                        "material": "corporate",
                        "reusable": True,
                        "meaningful": True,
                        "evidence_kind": "observed",
                    },
                },
            )
            assert result.data["decision"] == "save"
            result = await client.call_tool(
                "capture_memory", {"candidate": result.data["candidate"]}
            )
            assert result.data["status"] == "saved"
            result = await client.call_tool(
                "capture_memory", {"candidate": dict(candidate, scope="personal")}
            )
            assert result.data["status"] == "failed"
            result = await client.call_tool("search_memory", {"query": "git"})
            assert result.data["provider"] == "basic-memory", result.data
            assert result.data["notes"][0]["id"] == candidate["id"]
            result = await client.call_tool("memory_status", {"check_provider": True})
            assert result.data["provider_check"]["status"] == "available", result.data
            if args.next_release_dir:
                blocked = subprocess.run(
                    [
                        sys._base_executable,
                        "-I",
                        str(root / "shiori.py"),
                        "update",
                        "--release-dir",
                        str(args.next_release_dir),
                        "--apply",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )
                assert blocked.returncode == 1 and "Close all managed" in blocked.stderr

    asyncio.run(stdio())
    before = cli("run", "read", candidate["id"])
    launchers = {name: (root / name).read_bytes() for name in ["shiori.py", "shiori.cmd"]}
    original_config = (root / "data/config.json").read_bytes()
    if args.next_release_dir:
        assert cli("update", "--release-dir", str(args.next_release_dir))["applied"] is False
        assert (
            cli("update", "--release-dir", str(args.next_release_dir), "--apply")["status"]
            == "updated"
        )
        assert cli("status")["active"] != first
        assert cli("run", "read", candidate["id"]) == before
        later = dict(candidate, id="after-update", event_id="after-update")
        event_file = temporary / "synthetic-event.json"
        event_file.write_text(json.dumps(later), encoding="utf-8")
        assert cli("run", "capture", "--event-file", str(event_file))["status"] == "saved"
        assert cli("rollback", "--apply")["status"] == "rolled-back"
        assert cli("status")["active"] == first
        assert cli("run", "read", candidate["id"]) == before
        assert "git --version" in cli("run", "read", "after-update")
        assert len(list((root / "recovery").glob("*/memory/manifest.json"))) == 2
    assert (root / "data/config.json").read_bytes() == original_config
    assert all((root / name).read_bytes() == raw for name, raw in launchers.items())
    Brain(load_config(root / "data/config.json")).read(candidate["id"])
    if os.name == "nt":
        shim = subprocess.run(
            [str(root / "shiori.cmd"), "run", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert shim.returncode == 0 and json.loads(shim.stdout)["scope"] == "work", shim.stderr
    print(
        json.dumps(
            {
                "status": "passed",
                "scope": "work",
                "data": "synthetic-only",
                "checks": [
                    "package-install",
                    "stable-launcher",
                    "stdio-eight-tools",
                    "scope-rejection",
                    "owned-skill",
                    "real-isolated-provider",
                ],
                "two_version_update_rollback": bool(args.next_release_dir),
            }
        )
    )


if __name__ == "__main__":
    main()
