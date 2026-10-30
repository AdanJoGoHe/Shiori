"""Installed-wheel and optional two-version work-runtime check; synthetic data only."""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastmcp import Client
from packaging.version import Version

from second_brain.core import Brain, load_config
from second_brain.runtime import python_in


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--next-release-dir", type=Path)
    parser.add_argument(
        "--simulate-online",
        action="store_true",
        help="Synthetic GitHub responses; real downloaded-wheel installation",
    )
    args = parser.parse_args()
    if args.simulate_online and not args.next_release_dir:
        parser.error("--simulate-online requires --next-release-dir")
    release = args.release_dir.resolve()
    temporary = Path(tempfile.mkdtemp(prefix="shiori-work-check-"))
    incoming = temporary / "Release café files"
    incoming.mkdir()
    for path in release.iterdir():
        if path.name in {"SHA256SUMS", "install-shiori.ps1"} or path.name.endswith(
            (".whl", "-constraints.txt")
        ):
            # Dist may contain older bundles; copy only this installed verifier's release.
            from importlib.metadata import version

            if (
                path.name not in {"SHA256SUMS", "install-shiori.ps1"}
                and f"-{version('second-brain')}-" not in path.name
            ):
                continue
            shutil.copyfile(path, incoming / path.name)
    release = incoming
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

    # Exercise the actual managed launcher; no host configuration or real memory is used.
    launcher = (
        [str(root / "shiori.cmd")]
        if os.name == "nt"
        else [sys._base_executable, "-I", str(root / "shiori.py")]
    )

    def agent_cli(*arguments, payload=None):
        return subprocess.run(
            [*launcher, "run", *arguments],
            input=None if payload is None else json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    for flag in ("--help", "-h"):
        help_result = agent_cli(flag)
        assert (
            help_result.returncode == 0
            and "note" in help_result.stdout
            and "--config" not in help_result.stdout
        )
    for arguments in [(), ("sarch",)]:
        unknown = agent_cli(*arguments)
        assert (
            unknown.returncode != 0 and "note" in unknown.stderr and "run --help" in unknown.stderr
        )
    assert agent_cli("search", "--help").returncode == 0
    request = {
        "candidate": {
            "scope": "work",
            "id": "agent-fixture",
            "event_id": "agent-fixture",
            "title": "Agent workflow fixture",
            "type": "knowledge",
            "status": "verified",
            "source_agent": "manual",
            "project": "agent-cli",
            "tags": ["kubernetes"],
            "body": "Comprobación ágil 😀\nSolo datos ficticios.",
            "evidence": "Synthetic fixture",
        },
        "assessment": {
            "material": "corporate",
            "reusable": True,
            "meaningful": True,
            "evidence_kind": "none",
        },
    }
    preview = agent_cli("note", "--request-file", "-", payload=request)
    assert preview.returncode == 0 and not json.loads(preview.stdout)["applied"]
    assert cli("run", "status")["notes"] == 0
    saved = agent_cli("note", "--request-file", "-", "--apply", payload=request)
    assert saved.returncode == 0 and json.loads(saved.stdout)["candidate"]["status"] == "unverified"
    exact = agent_cli("search", "--id", "agent-fixture")
    assert json.loads(exact.stdout)["found"]
    assert json.loads(agent_cli("search", "--id", "missing").stdout)["found"] is False
    assert (
        json.loads(agent_cli("search", "--tag", " KUBERNETES ").stdout)[0]["id"] == "agent-fixture"
    )
    text = agent_cli("read", "agent-fixture", "--format", "text")
    assert text.returncode == 0 and text.stdout == cli("run", "read", "agent-fixture")
    assert "Comprobación ágil 😀\nSolo datos" in text.stdout and "status: unverified" in text.stdout
    changed = json.loads(json.dumps(request))
    changed["candidate"].update(
        event_id="agent-updated", body="Comprobación ágil 😀\nOtro párrafo."
    )
    classified = json.loads(agent_cli("classify", "--request-file", "-", payload=changed).stdout)
    assert classified["decision"] == "update" and "+Otro párrafo." in classified["diff"]["text"]
    stale = agent_cli(
        "note", "--request-file", "-", "--apply", "--expect-revision", "absent", payload=changed
    )
    assert stale.returncode != 0 and json.loads(stale.stdout)["capture"]["status"] == "blocked"
    assert agent_cli("capture", "--event-file", "-", payload=changed).returncode != 0
    captured = agent_cli("capture", "--event-file", "-", payload=classified["candidate"])
    assert json.loads(captured.stdout)["status"] == "saved"
    assert (
        json.loads(
            agent_cli("capture", "--event-file", "-", payload=classified["candidate"]).stdout
        )["status"]
        == "duplicate"
    )

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
            assert len(await client.list_tools()) == 10
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
            diary = await client.call_tool("read_journal", {"project": "synthetic"})
            assert diary.data["scope"] == "work" and diary.data["total"] == 1
            assert cli("run", "journal", "--project", "synthetic")["total"] == 1
            tracking = {
                "scope": "work",
                "mode": "journal-only",
                "event_id": "synthetic-tracking",
                "title": "Synthetic host follow-up",
                "source_agent": "augment-jetbrains",
                "project": "synthetic",
                "summary": "Track a disposable validation step.",
                "tasks": [
                    {
                        "id": "host-check",
                        "title": "Validate the synthetic host",
                        "status": "open",
                        "details": "Disposable fixture",
                        "version": 0,
                    }
                ],
            }
            saved = await client.call_tool("capture_memory", {"candidate": tracking})
            assert saved.data["status"] == "saved"
            resumed = await client.call_tool("resume_project", {"project": "synthetic"})
            assert resumed.data["active_tasks"][0]["version"] == 1
            assert cli("run", "project-resume", "synthetic")["active_total"] == 1
            states = await client.call_tool(
                "read_journal", {"project": "synthetic", "view": "tasks"}
            )
            assert states.data["tasks"][0]["history_total"] == 1
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
    assert cli("run", "learn", "guide")["scope"] == "work"
    proposal = {
        "scope": "work",
        "id": "synthetic-workflow",
        "source_id": candidate["id"],
        "project": "synthetic",
        "description": "Synthetic Git workflow for package verification",
        "instructions": "1. Run git --version.\n2. Inspect the observed version.",
        "change": "correction",
        "capabilities": ["read", "run-commands"],
    }
    proposal_file = temporary / "synthetic-proposal.json"
    proposal_file.write_text(json.dumps(proposal), encoding="utf-8")
    assert cli("run", "learn", "propose", "--request-file", str(proposal_file), "--apply")[
        "applied"
    ]
    activation = cli(
        "run",
        "learn",
        "activate",
        "--id",
        proposal["id"],
        "--host",
        "augment",
        "--skills-dir",
        str(skills),
        "--apply",
    )
    assert activation["applied"] and Path(activation["paths"][0]).is_file()
    assert (
        cli("run", "learn", "check", "--id", proposal["id"], "--expect-revision", "1")["status"]
        == "ready"
    )
    before = cli("run", "read", candidate["id"])
    launchers = {name: (root / name).read_bytes() for name in ["shiori.py", "shiori.cmd"]}
    original_config = (root / "data/config.json").read_bytes()
    if args.next_release_dir:
        assert cli("update", "--release-dir", str(args.next_release_dir))["applied"] is False
        if args.simulate_online:
            import hashlib
            from second_brain.runtime import release_bundle

            next_release = args.next_release_dir.resolve()
            next_version = release_bundle(next_release)["version"]
            parsed = Version(next_version)
            tag = "v" + parsed.base_version
            if parsed.pre:
                tag += (
                    "-"
                    + {"a": "alpha", "b": "beta", "rc": "rc"}[parsed.pre[0]]
                    + "."
                    + str(parsed.pre[1])
                )
            metadata = {
                "tag_name": tag,
                "draft": False,
                "prerelease": parsed.is_prerelease,
                "published_at": "2026-10-26T00:00:00Z",
                "assets": [],
            }
            payloads = {}
            for index, path in enumerate(sorted(next_release.iterdir()), 1):
                if path.name != "SHA256SUMS" and not path.name.endswith(
                    (".whl", "-constraints.txt")
                ):
                    continue
                metadata["assets"].append(
                    {
                        "id": index,
                        "name": path.name,
                        "state": "uploaded",
                        "size": path.stat().st_size,
                        "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
                payloads[str(index)] = str(path)
            fixture = temporary / "synthetic-release.json"
            fixture.write_text(
                json.dumps({"metadata": metadata, "payloads": payloads}), encoding="utf-8"
            )
            script = (
                "import json,sys; from pathlib import Path; from second_brain import updater; "
                "fixture=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')); "
                "updater.fetch=lambda url,limit,binary=False: "
                "Path(fixture['payloads'][url.rsplit('/',1)[1]]).read_bytes() if binary else "
                "json.dumps([fixture['metadata']]).encode(); "
                "preview=updater.update(Path(sys.argv[1]),prerelease=True); "
                "assert preview['status']=='available' and not preview['applied']; "
                "result=updater.update(Path(sys.argv[1]),prerelease=True,apply=True); "
                "assert result['status']=='updated' and result['skill']=='updated'; "
                "print(json.dumps(result))"
            )
            applied = subprocess.run(
                [str(executable), "-I", "-X", "utf8", "-c", script, str(root), str(fixture)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=600,
            )
            assert applied.returncode == 0, applied.stderr
        else:
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
                    "stdio-ten-tools",
                    "scope-rejection",
                    "owned-skill",
                    "real-isolated-provider",
                    "managed-learning-proposal-activation",
                    "agent-cli-help-exact-search-stdin-diff-note",
                ],
                "two_version_update_rollback": bool(args.next_release_dir),
                "online_metadata": "synthetic" if args.simulate_online else "not-used",
            }
        )
    )


if __name__ == "__main__":
    main()
