import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastmcp import Client

from second_brain.agent_log import AgentLog
from second_brain.annotations import Conflict
from second_brain.backup import backup, restore
from second_brain.checkpoints import read_plan, record_checkpoint
from second_brain.core import Brain, PENDING_CHECKPOINT, load_config
from second_brain.server import create_server
from second_brain.task_pages import FIELDS, TaskPages
from second_brain.viewer import ViewerServer
from second_brain.work_context import build_work_context
from test_agent_log import action
from test_core import event
from test_work_context import NOW, brain as brain, create_page


def checkpoint(brain, **changes):
    return {
        "scope": brain.scope,
        "issue_key": "demo-1",
        "event_id": "checkpoint-demo",
        "expected_version": 1,
        "source_agent": "manual",
        "summary": "Reviewed a synthetic run",
        "progress": {
            "completed": ["Checked the fixture"],
            "decisions": ["Keep the gate"],
            "next_steps": ["Rerun the fixture"],
        },
        **changes,
    }


def knowledge():
    return dict(
        id="fixture-command",
        type="command",
        title="Check a synthetic fixture",
        status="verified",
        body="Use `echo fixture`.",
        evidence="Observed on a disposable fixture.",
    )


def reviewed_action(brain, project="demo"):
    return {**action(brain.scope), "event_id": "checkpoint-demo", "project": project}


def test_checkpoint_mcp_updates_existing_task_and_keeps_authored_body(brain):
    create_page(brain, body="## Original body\n\nKeep these notes.")
    request = checkpoint(brain, status="blocked")

    async def exercise():
        async with Client(create_server(brain.config)) as client:
            args = {"candidate": request}
            saved = (await client.call_tool("record_checkpoint", args)).data
            assert (saved["status"], saved["version"]) == ("saved", 2)
            assert saved["note_id"] is None and not saved["agent_log"]
            duplicate = (await client.call_tool("record_checkpoint", args)).data
            assert (duplicate["status"], duplicate["version"]) == ("duplicate", 2)
            work = (await client.call_tool("get_work_context", {"issue_key": "DEMO-1"})).data
            assert work["recent_progress"][0]["suggested_next_step"] == "Rerun the fixture"
            assert work["task"]["status"] == "blocked"
            status = (await client.call_tool("memory_status", {})).data
            assert status["pending_checkpoint"] is None

    asyncio.run(exercise())
    store = TaskPages(brain)
    page = store.read("demo-1")
    assert page["body"] == "## Original body\n\nKeep these notes."
    assert "Rerun the fixture" in store.markdown(page)
    assert brain.ledger()["notes"] == {}
    assert not (brain.state / "agent-log.json").exists()
    manual = {field: page[field] for field in FIELDS}
    updated = store.save(dict(manual, body="Edited manually", version=2))
    assert updated["checkpoint"] == page["checkpoint"]
    assert store.edit("demo-1", 3, {"status": "done"}, "later-edit")["version"] == 4
    assert store.read("demo-1")["checkpoint"] == page["checkpoint"]
    assert record_checkpoint(brain, request)["version"] == 2
    assert (
        record_checkpoint(brain, {**request, "summary": "Changed"})["reason"] == "event-id-reused"
    )


def test_optional_knowledge_and_action_respect_profile_and_opt_in(brain):
    create_page(brain, project=None)
    request = checkpoint(brain, knowledge=knowledge(), agent_action=reviewed_action(brain, None))
    saved = record_checkpoint(brain, request)
    assert saved["note_id"] == "fixture-command" and not saved["agent_log"]
    assert not (brain.state / "agent-log.json").exists()
    pack = build_work_context(brain, "DEMO-1")
    assert pack["notes"][0]["id"] == "fixture-command"
    assert pack["notes"][0]["title"] == knowledge()["title"]
    assert pack["recent_progress"][0]["event_id"] == "checkpoint-demo"
    assert len(brain.ledger()["events"]) == 1

    log = AgentLog(brain)
    log.configure(True, 0)
    assert not record_checkpoint(brain, request)["agent_log"]
    rejected = record_checkpoint(
        brain,
        checkpoint(brain, event_id="other-checkpoint", expected_version=2, knowledge=knowledge()),
    )
    assert rejected["reason"] == "knowledge-id-already-exists"
    assert TaskPages(brain).read("demo-1")["version"] == 2 and read_plan(brain) is None


def test_recover_after_task_write_failure_without_duplicating_journal_or_log(brain, monkeypatch):
    create_page(brain)
    log = AgentLog(brain)
    log.configure(True, 0)
    request = checkpoint(brain, agent_action=reviewed_action(brain))

    def interrupted(*_):
        raise OSError("synthetic task write interruption")

    with monkeypatch.context() as patch:
        patch.setattr(TaskPages, "_write", interrupted)
        assert record_checkpoint(brain, request)["status"] == "pending"
    assert TaskPages(brain).read("demo-1")["version"] == 1
    assert read_plan(brain)["event_id"] == "checkpoint-demo"
    assert brain.capture(event(scope=brain.scope))["reason"] == "pending-checkpoint"
    assert log.record(action(brain.scope))["reason"] == "pending-checkpoint"
    assert (
        TaskPages(brain).edit("demo-1", 1, {"status": "done"}, "other")["reason"]
        == "pending-checkpoint"
    )
    page = TaskPages(brain).read("demo-1")
    with pytest.raises(Conflict, match="pending checkpoint"):
        TaskPages(brain).save({field: page[field] for field in FIELDS} | {"version": 1})
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = {field: page[field] for field in FIELDS} | {"version": 1}
            with pytest.raises(HTTPError) as blocked:
                urlopen(
                    Request(
                        server.url + "api/tasks",
                        data=json.dumps(payload).encode(),
                        headers={"Origin": server.origin, "Content-Type": "application/json"},
                    ),
                    timeout=5,
                )
            assert blocked.value.code == 423
        finally:
            server.shutdown()
            thread.join(5)
    assert (
        record_checkpoint(brain, {**request, "event_id": "other"})["pending_event_id"]
        == "checkpoint-demo"
    )
    assert (
        record_checkpoint(brain, {**request, "summary": "Different"})["reason"] == "event-id-reused"
    )
    log.configure(False, log.status()["revision"])
    with pytest.raises(Conflict, match="pending checkpoint"):
        log.configure(True, log.status()["revision"])
    brain.pause(True)
    assert record_checkpoint(brain, request)["reason"] == "paused"
    brain.pause(False)

    saved = record_checkpoint(brain, request)
    assert saved["version"] == 2 and saved["agent_log"] is True
    assert read_plan(brain) is None
    logs = log.export()["items"]
    assert len(logs) == 1 and logs[0]["event_id"] == "checkpoint-demo"
    assert {(ref["kind"], ref["target"]) for ref in logs[0]["references"]} == {
        ("content", f"task:{brain.scope}:DEMO-1"),
        ("journal-event", "checkpoint-demo"),
    }
    journal = brain.path(brain.ledger()["events"]["checkpoint-demo"]["path"])
    assert journal.read_text(encoding="utf-8").count("<!-- event:checkpoint-demo -->") == 1


def test_partial_note_capture_survives_backup_and_retries_on_original_day(
    brain, tmp_path, monkeypatch
):
    from second_brain import core

    create_page(brain)
    request = checkpoint(brain, knowledge=knowledge())
    write = core.atomic_write

    def fail_journal(path, value):
        if path.name == "2026-11-09.md":
            raise OSError("synthetic failure after writing the note")
        write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(core, "atomic_write", fail_journal)
        assert record_checkpoint(brain, request)["status"] == "pending"
    assert brain.ledger()["events"]["checkpoint-demo"]["status"] == "pending"
    assert brain.ledger()["notes"] == {}
    backup(brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    recovered = Brain(load_config(tmp_path / "restored" / "config.json"))
    recovered.now = lambda: NOW + timedelta(days=1)
    assert record_checkpoint(recovered, request)["reason"] == "paused"
    recovered.pause(False)
    assert record_checkpoint(recovered, request)["status"] == "saved"
    assert read_plan(recovered) is None
    entries = build_work_context(recovered, "demo-1")["recent_progress"]
    assert len(entries) == 1 and entries[0]["path"] == "journal/2026/2026-11-09.md"
    assert "echo fixture" in recovered.read("fixture-command")
    assert record_checkpoint(recovered, request)["status"] == "duplicate"


def test_concurrent_checkpoints_and_invalid_input_do_not_partially_commit(brain):
    create_page(brain)
    with pytest.raises(ValueError):
        record_checkpoint(brain, checkpoint(brain, progress={"next_steps": [None]}))
    with pytest.raises(ValueError):
        record_checkpoint(brain, checkpoint(brain, scope="other"))
    assert read_plan(brain) is None and brain.ledger()["events"] == {}

    def submit(event_id):
        return record_checkpoint(brain, checkpoint(brain, event_id=event_id))

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(submit, ["one", "two"]))
    assert sorted(row["status"] for row in results) == ["conflict", "saved"]
    assert len(brain.ledger()["events"]) == 1 and TaskPages(brain).read("demo-1")["version"] == 2


def test_checkpoint_reserves_no_intent_when_journal_is_full(brain, monkeypatch):
    create_page(brain)
    monkeypatch.setattr("second_brain.checkpoints.MAX_DAY_BYTES", 512)
    with pytest.raises(ValueError, match="insufficient space"):
        record_checkpoint(brain, checkpoint(brain))
    assert read_plan(brain) is None and brain.ledger()["events"] == {}
    assert TaskPages(brain).read("DEMO-1")["version"] == 1


def test_checkpoint_retry_cleans_up_after_final_receipt_was_saved(brain, monkeypatch):
    create_page(brain)
    request = checkpoint(brain)
    unlink = Path.unlink

    def interrupted(path, *args, **kwargs):
        if path.name == PENDING_CHECKPOINT:
            raise OSError("synthetic interruption after the task receipt")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupted)
        assert record_checkpoint(brain, request)["status"] == "pending"
    assert read_plan(brain) and TaskPages(brain).read("DEMO-1")["version"] == 2
    brain.pause(True)
    assert record_checkpoint(brain, request)["status"] == "duplicate"
    assert read_plan(brain) is None and len(brain.ledger()["events"]) == 1
