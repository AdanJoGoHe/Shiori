"""Check an actual older bundle -> candidate -> rollback using disposable work memory."""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from fastmcp import Client
from packaging.version import Version

from second_brain.runtime import python_in, release_bundle
from second_brain.core import Brain, load_config
from recovery_check import verify_recovery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-release", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    args = parser.parse_args()
    old = release_bundle(args.previous_release.resolve())
    new = release_bundle(args.release_dir.resolve())
    assert Version(new["version"]) > Version(old["version"])
    assert Version(version("second-brain")) == Version(new["version"]), (
        "Run with the installed candidate wheel"
    )
    checkpoint_tools = Version(new["version"]) >= Version("0.1.0a8")
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

        def check_refreshed_skill():
            assert owned.read_bytes() != original_skill
            if checkpoint_tools:
                from second_brain.runtime import work_skill_files

                for name, content in work_skill_files().items():
                    assert (owned.parent / name).read_text(encoding="utf-8") == content
            else:
                assert b"resume_project" in owned.read_bytes()

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
        check_refreshed_skill()
        assert cli("run", "read", candidate["id"]) == before
        assert (root / "data/state/annotations.json").read_bytes() == annotations

        agent_cli = Version(new["version"]) >= Version("0.1.0a6")
        if agent_cli:
            assert cli("run", "search", "--id", candidate["id"])["found"]
            request = dict(
                candidate=dict(candidate, id="upgrade-cli", event_id="upgrade-cli"),
                assessment=dict(
                    material="corporate", reusable=True, meaningful=True, evidence_kind="observed"
                ),
            )
            event.write_text(json.dumps(request), encoding="utf-8")
            assert cli("run", "note", "--request-file", str(event))["applied"] is False
            assert not cli("run", "search", "--id", "upgrade-cli")["found"]
            saved = cli(
                "run",
                "note",
                "--request-file",
                str(event),
                "--apply",
                "--expect-revision",
                "absent",
            )
            assert saved["capture"]["status"] == "saved"
            assert cli("run", "search", "--id", "upgrade-cli")["found"]

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
        if agent_cli:
            assert "Synthetic memory" in cli("run", "read", "upgrade-cli")
        assert all(path.read_bytes() == content for path, content in journal.items())
        assert (root / "data/state/annotations.json").read_bytes() == annotations
        # The saved previous environment is reactivated by rollback; update refuses existing dirs.
        assert cli("rollback", "--apply")["status"] == "rolled-back"
        assert cli("status")["active"] == new["version"]
        assert cli("augment", "--skills-dir", str(skills), "--apply")["applied"]
        check_refreshed_skill()
        assert cli("run", "project-resume", "release-check")["active_tasks"] == pack["active_tasks"]
        assert foreign.read_text(encoding="utf-8") == "Synthetic independent skill"
        assert (root / "data/config.json").read_bytes() == configuration
        recovery = verify_recovery(
            Brain(load_config(root / "data/config.json")), Path(folder) / "current-data"
        )
        checkpoint = dict(
            scope="work",
            issue_key="DEMO-1234",
            event_id="upgrade-checkpoint",
            expected_version=1,
            source_agent="manual",
            summary="Checked the synthetic rollout.",
            progress={"next_steps": ["Recheck the fixture."]},
        )
        if checkpoint_tools:

            async def save_checkpoint():
                transport = {
                    "mcpServers": {
                        "work": {
                            "command": sys._base_executable,
                            "args": ["-I", str(root / "shiori.py"), "run", "serve"],
                        }
                    }
                }
                async with Client(transport) as client:
                    page = await client.call_tool("get_task_page", {"issue_key": "DEMO-1234"})
                    assert page.data["version"] == 1
                    reply = await client.call_tool("record_checkpoint", {"candidate": checkpoint})
                    assert reply.data["status"] == "saved" and reply.data["version"] == 2
                    work = await client.call_tool("get_work_context", {"issue_key": "DEMO-1234"})
                    assert (
                        work.data["recent_progress"][0]["suggested_next_step"]
                        == "Recheck the fixture."
                    )

            asyncio.run(save_checkpoint())
            assert (
                json.loads((root / "data/state/task-pages.json").read_bytes())["schema_version"]
                == 3
            )
        protected = {path: path.read_bytes() for path in (root / "data/vault").rglob("*.md")}
        protected.update({path: path.read_bytes() for path in (root / "data/state").glob("*.json")})
        protected.update(
            {
                root / name: (root / name).read_bytes()
                for name in ["installation.json", "shiori.py", "shiori.cmd"]
            }
        )
        previous_checkpoints = set((root / "recovery").iterdir())
        refused = cli("rollback", "--apply", success=False)
        assert cli("status")["active"] == new["version"]
        assert all(path.read_bytes() == raw for path, raw in protected.items())
        checkpoints = set((root / "recovery").iterdir()) - previous_checkpoints
        assert len(checkpoints) == 1
        from second_brain.backup import read_bundle, restore

        bundle = next(iter(checkpoints)) / "memory"
        _, saved, _ = read_bundle(bundle, "work")
        assert {
            "state/favorites.json",
            "state/task-pages.json",
            "state/agent-log.json",
        } <= saved.keys()
        assert refused.returncode != 0
        if checkpoint_tools:
            from second_brain.checkpoints import record_checkpoint
            from second_brain.task_pages import TaskPages

            recovered = Path(folder) / "checkpoint-restored"
            assert restore(bundle, recovered)["paused"]
            brain = Brain(load_config(recovered / "config.json"))
            assert (brain.state / "task-pages.json").read_bytes() == saved["state/task-pages.json"]
            assert (
                TaskPages(brain).read("DEMO-1234")["checkpoint"]["event_id"]
                == checkpoint["event_id"]
            )
            replay = record_checkpoint(brain, checkpoint)
            assert replay["status"] == "duplicate" and replay["version"] == 2
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
                        "incompatible-rollback-refused-with-new-sidecars",
                        "failed-rollback-preserves-data-launchers-and-recovery",
                    ]
                    + (["agent-cli-preview-apply-after-upgrade"] if agent_cli else [])
                    + (
                        [
                            "skill-references-refresh",
                            "checkpoint-receipt-restored",
                            "schema-3-rollback-refused",
                        ]
                        if checkpoint_tools
                        else []
                    ),
                    "data": "synthetic-only",
                    "full_recovery": recovery,
                }
            )
        )


if __name__ == "__main__":
    main()
