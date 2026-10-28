"""Check an actual older bundle -> candidate -> rollback using disposable work memory."""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from fastmcp import Client
from packaging.version import Version

from second_brain.runtime import python_in, release_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-release", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    args = parser.parse_args()
    old = release_bundle(args.previous_release.resolve())
    new = release_bundle(args.release_dir.resolve())
    assert Version(new["version"]) > Version(old["version"])
    with tempfile.TemporaryDirectory(prefix="shiori-release-pair-") as folder:
        root = Path(folder) / "Synthetic café memory"
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(args.previous_release.resolve() / "install-shiori.ps1"),
            "-ReleaseDir",
            str(args.previous_release.resolve()),
            "-InstallDir",
            str(root),
        ]
        preview = subprocess.run(command, capture_output=True, timeout=30)
        assert preview.returncode == 0 and not root.exists(), preview.stderr
        applied = subprocess.run([*command, "-Apply"], capture_output=True, timeout=600)
        assert applied.returncode == 0, applied.stderr

        def cli(*arguments, success=True):
            result = subprocess.run(
                [sys._base_executable, "-I", str(root / "shiori.py"), *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=600,
            )
            if success:
                assert result.returncode == 0, result.stderr
                return json.loads(result.stdout)
            assert result.returncode != 0
            return result

        assert cli("status")["active"] == old["version"]
        configuration = (root / "data/config.json").read_bytes()
        skills = Path(folder) / "synthetic-home/.augment/skills"
        owned = Path(cli("augment", "--skills-dir", str(skills), "--apply")["skill"])
        original_skill = owned.read_bytes()
        foreign = skills / "other/SKILL.md"
        foreign.parent.mkdir()
        foreign.write_text("Synthetic independent skill", encoding="utf-8")

        candidate = {
            "scope": "work",
            "id": "before-upgrade",
            "event_id": "before-upgrade",
            "title": "Synthetic pre-upgrade memory",
            "type": "knowledge",
            "status": "verified",
            "source_agent": "manual",
            "project": "release-check",
            "body": "Synthetic memory before upgrade.",
            "evidence": "Disposable release fixture.",
        }
        event = Path(folder) / "event.json"
        event.write_text(json.dumps(candidate), encoding="utf-8")
        assert cli("run", "capture", "--event-file", str(event))["status"] == "saved"
        before = cli("run", "read", candidate["id"])
        old_python = python_in(root, old["version"])
        script = (
            "import sys; from second_brain.core import Brain,load_config; "
            "from second_brain.viewer import Viewer; from second_brain.annotations import Annotations; "
            "b=Brain(load_config(sys.argv[1])); d=Viewer(b).content('note:work:before-upgrade'); "
            "start=d['text'].index('Synthetic'); "
            "Annotations(b).save(d,dict(document_id=d['item']['id'],revision=d['revision'],"
            "start=start,end=start+9,quote='Synthetic',color='yellow',tags=[]))"
        )
        marked = subprocess.run(
            [str(old_python), "-I", "-c", script, str(root / "data/config.json")],
            capture_output=True,
            timeout=30,
        )
        assert marked.returncode == 0, marked.stderr
        annotations = (root / "data/state/annotations.json").read_bytes()

        async def active_session_refusal():
            transport = {
                "mcpServers": {
                    "work": {
                        "command": sys._base_executable,
                        "args": ["-I", str(root / "shiori.py"), "run", "serve"],
                    }
                }
            }
            async with Client(transport) as client:
                status = await client.call_tool("memory_status", {})
                assert status.data["scope"] == "work"
                refused = cli(
                    "update",
                    "--release-dir",
                    str(args.release_dir.resolve()),
                    "--apply",
                    success=False,
                )
                assert "session" in refused.stderr.lower()
                assert cli("status")["active"] == old["version"]

        asyncio.run(active_session_refusal())
        assert cli("update", "--release-dir", str(args.release_dir.resolve()))["applied"] is False
        updated = cli("update", "--release-dir", str(args.release_dir.resolve()), "--apply")
        assert updated["status"] == "updated"
        # Local-bundle updates and rollback refresh the owned skill explicitly, as documented.
        assert cli("augment", "--skills-dir", str(skills), "--apply")["applied"]
        assert cli("status")["active"] == new["version"]
        assert b"resume_project" in owned.read_bytes() and owned.read_bytes() != original_skill
        assert cli("run", "read", candidate["id"]) == before
        assert (root / "data/state/annotations.json").read_bytes() == annotations

        tracking = dict(
            scope="work",
            mode="journal-only",
            source_agent="manual",
            project="release-check",
            event_id="after-upgrade-task",
            title="Synthetic next action",
            summary="Keep a tracked follow-up.",
            tasks=[
                dict(
                    id="host-check",
                    title="Check the synthetic host",
                    details="Fictitious content",
                    status="blocked",
                    version=0,
                )
            ],
        )
        event.write_text(json.dumps(tracking), encoding="utf-8")
        assert cli("run", "capture", "--event-file", str(event))["status"] == "saved"
        pack = cli("run", "project-resume", "release-check")
        assert pack["active_tasks"][0]["version"] == 1
        data = json.loads(configuration)
        vault = Path(data["vault_path"])
        later = dict(candidate, id="after-upgrade", event_id="after-upgrade")
        event.write_text(json.dumps(later), encoding="utf-8")
        assert cli("run", "capture", "--event-file", str(event))["status"] == "saved"
        journal = {path: path.read_bytes() for path in vault.glob("journal/*/*.md")}
        assert cli("rollback", "--apply")["status"] == "rolled-back"
        assert cli("status")["active"] == old["version"]
        assert cli("augment", "--skills-dir", str(skills), "--apply")["applied"]
        assert owned.read_bytes() == original_skill
        assert cli("run", "read", candidate["id"]) == before
        assert "Synthetic memory" in cli("run", "read", "after-upgrade")
        assert all(path.read_bytes() == content for path, content in journal.items())
        assert (root / "data/state/annotations.json").read_bytes() == annotations
        # The saved previous environment is reactivated by rollback; update refuses existing dirs.
        assert cli("rollback", "--apply")["status"] == "rolled-back"
        assert cli("status")["active"] == new["version"]
        assert cli("augment", "--skills-dir", str(skills), "--apply")["applied"]
        assert b"resume_project" in owned.read_bytes()
        assert cli("run", "project-resume", "release-check")["active_tasks"] == pack["active_tasks"]
        assert foreign.read_text(encoding="utf-8") == "Synthetic independent skill"
        assert (root / "data/config.json").read_bytes() == configuration
        print(
            json.dumps(
                {
                    "status": "passed",
                    "from": old["version"],
                    "to": new["version"],
                    "checks": [
                        "old-bundle-install",
                        "active-session-refusal",
                        "owned-skill-refresh",
                        "notes-and-marks-preserved",
                        "rollback-preserves-newer-data",
                        "reactivation-preserves-task-state",
                    ],
                    "data": "synthetic-only",
                }
            )
        )


if __name__ == "__main__":
    main()
