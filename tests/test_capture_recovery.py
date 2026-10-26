import asyncio
import json
import subprocess
import sys
from datetime import datetime

import pytest
from fastmcp import Client

from second_brain import core
from second_brain.server import create_server
from test_core import brain as brain, event


@pytest.mark.parametrize("failure", ["pending", "note", "journal", "commit"])
@pytest.mark.parametrize("updating", [False, True])
def test_retry_after_restart_preserves_note_and_day(brain, monkeypatch, failure, updating):
    if updating:
        brain.capture(event(event_id="initial", project="one", tags=["python"]))
    moment = datetime.fromisoformat("2026-10-16T23:59:00+02:00")
    monkeypatch.setattr(brain, "now", lambda: moment)
    candidate = event(event_id="recover", body="Recovered observation")
    original = core.atomic_write

    def fail(path, content):
        if (
            (failure == "pending" and path == brain.ledger_path)
            or (failure == "note" and path == brain.path("commands/git-version.md"))
            or (failure == "journal" and "journal" in path.parts)
            or (
                failure == "commit"
                and path == brain.ledger_path
                and json.loads(content)["events"]["recover"]["status"] == "committed"
            )
        ):
            raise OSError("Synthetic interruption")
        original(path, content)

    monkeypatch.setattr(core, "atomic_write", fail)
    with pytest.raises(OSError, match="Synthetic"):
        brain.capture(candidate)
    monkeypatch.setattr(core, "atomic_write", original)
    fresh = core.Brain(brain.config)
    monkeypatch.setattr(fresh, "now", lambda: moment.replace(day=17, hour=0, minute=1))
    if failure != "pending":
        before = {p: p.read_bytes() for p in brain.vault.rglob("*.md")}
        blocked = fresh.capture(event(event_id="later", body="Later observation", type="lesson"))
        assert blocked == {
            "status": "blocked",
            "reason": "pending-note-capture",
            "id": "git-version",
            "event_id": "recover",
        }
        assert before == {p: p.read_bytes() for p in brain.vault.rglob("*.md")}
        assert "later" not in fresh.ledger()["events"]
        with pytest.raises(ValueError, match="reused"):
            fresh.capture(dict(candidate, body="Changed payload"))
        fresh.pause(True)
        assert fresh.capture(candidate) == {"status": "skipped", "reason": "paused"}
        assert fresh.pending_captures()["total"] == 1
        fresh.pause(False)
        # Other notes remain usable, including when they share the journal.
        assert fresh.capture(event(id="other", event_id="other-event"))["status"] == "saved"
    saved = fresh.capture(candidate)
    assert saved["status"] == "saved"
    assert saved["journal"].endswith("2026-10-17.md" if failure == "pending" else "2026-10-16.md")
    assert fresh.capture(candidate)["status"] == "duplicate"
    assert fresh.status()["pending"] == 0
    assert "Recovered observation" in fresh.read("git-version")
    if updating:
        assert "project: one" in fresh.read("git-version")
        assert "- python" in fresh.read("git-version")
        assert len(list(brain.path("archive/git-version").glob("*.md"))) == 1
    assert (
        fresh.path(saved["journal"]).read_text(encoding="utf-8").count("<!-- event:recover -->")
        == 1
    )


def test_pending_mcp_cli_and_read_only_pagination(brain, tmp_path):
    # Legacy pending events contain identifiers/hash/date/path, never payloads.
    ledger = {"notes": {}, "events": {}}
    for i in range(3):
        ledger["events"][f"pending-{i}"] = {
            "status": "pending",
            "fingerprint": "a" * 64,
            "path": f"knowledge/note-{i}.md",
            "at": "2026-10-16T10:00:00+02:00",
        }
    ledger["events"]["done"] = dict(ledger["events"]["pending-0"], status="committed")
    core.atomic_write(brain.ledger_path, json.dumps(ledger))
    before = brain.ledger_path.read_bytes()
    page = brain.pending_captures(offset=1, limit=1)
    assert page["total"] == 3 and page["next_offset"] == 2
    assert page["events"] == [{"event_id": "pending-1", **ledger["events"]["pending-1"]}]
    assert brain.pending_captures(offset=3)["events"] == []
    for kwargs in [{"offset": -1}, {"limit": 0}, {"limit": 101}, {"limit": True}]:
        with pytest.raises(ValueError):
            brain.pending_captures(**kwargs)

    async def scenario():
        async with Client(create_server(brain.config)) as client:
            result = await client.call_tool("list_pending_captures", {"offset": 1, "limit": 1})
            assert result.data == page

    asyncio.run(scenario())
    config = tmp_path / "config.json"
    config.write_text(json.dumps(dict(brain.config, schema_version=1)), encoding="utf-8")

    async def stdio_scenario():
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
            assert "list_pending_captures" in {t.name for t in await client.list_tools()}
            result = await client.call_tool("list_pending_captures", {"offset": 1, "limit": 1})
            assert result.data == page

    asyncio.run(stdio_scenario())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "second_brain.cli",
            "--config",
            str(config),
            "pending",
            "--offset",
            "1",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == page
    assert brain.ledger_path.read_bytes() == before
    assert list(brain.vault.rglob("*.md")) == []
