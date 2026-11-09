import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain.core import Brain
from second_brain.server import create_server
from second_brain.task_pages import TaskPages
from second_brain.work_context import build_work_context
from test_core import event

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


@pytest.fixture(params=["personal", "work"])
def brain(tmp_path, request):
    store = Brain(
        dict(
            scope=request.param,
            timezone="UTC",
            vault_path=str(tmp_path / "vault"),
            state_path=str(tmp_path / "state"),
        )
    )
    store.now = lambda: NOW
    return store


def journal(brain, event_id, **changes):
    return brain.capture(
        {
            "scope": brain.scope,
            "mode": "journal-only",
            "event_id": event_id,
            "title": "Synthetic progress",
            "summary": "Review completed",
            "source_agent": "manual",
            "project": "demo",
            **changes,
        }
    )


def create_page(brain, **changes):
    result = TaskPages(brain).edit(
        "DEMO-1", 0, {"title": "Synthetic task", "project": "demo", **changes}, "create-task"
    )
    assert result["status"] == "saved"


def note_link(brain, note_id):
    return dict(target=f"note:{brain.scope}:{note_id}", annotation_id=None, label=note_id)


def test_exact_issue_pack_excludes_nearby_issues_and_respects_corrections(brain):
    brain.now = lambda: NOW - timedelta(days=31)
    journal(brain, "too-old", title="DEMO-1 old history")
    brain.now = lambda: NOW - timedelta(days=1)
    journal(brain, "exact-title", title="Review (demo-1)")
    journal(brain, "same-project", title="Other progress")
    journal(brain, "similar-code", title="DEMO-10 progress")
    journal(brain, "wrong-project", title="DEMO-1", project="other")
    journal(brain, "wrong-activity", activity="demo-10", title="Mentions DEMO-1")
    journal(brain, "original", activity="demo-1", summary="Obsolete next step")
    journal(
        brain,
        "correction",
        supersedes=["original"],
        change_reason="The check is still pending",
        summary="Configuration reviewed",
        progress={"next_steps": ["Run the synthetic check", "Open the fixture"]},
    )
    brain.now = lambda: NOW
    create_page(brain, status="blocked", body="Waiting for the check.")

    pack = build_work_context(brain, "demo-1")
    assert pack["task"]["status"] == "blocked"
    assert pack["task"]["version"] == 1 and pack["task"]["id"] == f"task:{brain.scope}:DEMO-1"
    assert pack["task"]["body_excerpt"] == "Waiting for the check."
    assert [row["event_id"] for row in pack["recent_progress"]] == ["correction", "exact-title"]
    first = pack["recent_progress"][0]
    assert first["suggested_next_step"] == "Run the synthetic check"
    assert first["summary"] == "Configuration reviewed"
    assert first["path"] == "journal/2026/2026-11-08.md"
    assert "progress-predates-task-update" in pack["warnings"]
    assert pack["notes"] == [] and pack["recent_days"] == 31


def test_linked_notes_use_exact_records_revision_and_freshness(brain):
    brain.now = lambda: NOW - timedelta(days=91)
    for note_id, status in [
        ("linked", "verified"),
        ("historical", "obsolete"),
        ("missing", "unverified"),
        ("unlinked", "verified"),
    ]:
        brain.capture(
            event(
                scope=brain.scope,
                id=note_id,
                event_id=f"note-{note_id}",
                title=f"DEMO-1 {note_id}",
                body="Synthetic knowledge.",
                status=status,
            )
        )
    brain.now = lambda: NOW
    create_page(brain, links=[note_link(brain, key) for key in ("linked", "historical", "missing")])
    brain.path(brain.ledger()["notes"]["missing"]).unlink()

    pack = build_work_context(brain, "DEMO-1", include=["notes"])
    assert "task" not in pack and "recent_progress" not in pack
    assert pack["warnings"] == ["linked-note-unavailable"]
    assert [row["id"] for row in pack["notes"]] == ["linked", "historical"]
    linked, historical = pack["notes"]
    assert linked["revision"] == hashlib.sha256(brain.read("linked").encode()).hexdigest()
    assert linked["excerpt"] == "Synthetic knowledge.\n"
    assert linked["age_days"] == 91
    assert "verification-at-least-90-days-old" in linked["warnings"]
    assert "historical-note" in historical["warnings"] and "excerpt" not in historical


def test_budget_keeps_core_state_and_recorded_step_and_reports_incomplete_journal(brain):
    create_page(brain, body="Long body 🧠\n" * 800)
    brain.now = lambda: NOW - timedelta(days=1)
    older = journal(brain, "unreadable", activity="demo-1")
    brain.now = lambda: NOW
    journal(
        brain,
        "latest",
        activity="demo-1",
        summary='Text with "quotes" and emoji 🧠. ' * 25,
        progress={"next_steps": ['Run "echo fixture" 🧠']},
    )
    brain.path(older["journal"]).unlink()
    for budget in (1000, 1500, 10000, 20000):
        pack = build_work_context(brain, "DEMO-1", budget)
        assert len(json.dumps(pack, ensure_ascii=False)) <= budget
        assert pack["truncated"] and "journal-incomplete" in pack["warnings"]
        assert pack["task"]["status"] == "open"
        assert pack["recent_progress"][0]["suggested_next_step"] == 'Run "echo fixture" 🧠'


def test_mcp_missing_and_selective_reads(brain, monkeypatch):
    create_page(brain)

    def unexpected(*args):
        pytest.fail("Unrequested section must not be read")

    monkeypatch.setattr("second_brain.work_context.issue_progress", unexpected)
    monkeypatch.setattr("second_brain.work_context.linked_notes", unexpected)

    async def exercise():
        async with Client(create_server(brain.config)) as client:
            missing = await client.call_tool("get_work_context", {"issue_key": "DEMO-10"})
            assert missing.data["found"] is False
            selected = await client.call_tool(
                "get_work_context", {"issue_key": "demo-1", "include": ["task"]}
            )
            assert selected.data["scope"] == brain.scope and selected.data["found"]
            assert selected.data["task"]["title"] == "Synthetic task"
            assert "notes" not in selected.data and "recent_progress" not in selected.data
            for invalid in (
                {"include": ["notes", "notes"]},
                {"include": ["agent_log"]},
                {"max_chars": "10000"},
                {"max_chars": 999},
                {"issue_key": "../other"},
            ):
                with pytest.raises(ToolError):
                    await client.call_tool("get_work_context", {"issue_key": "DEMO-1", **invalid})

    asyncio.run(exercise())
