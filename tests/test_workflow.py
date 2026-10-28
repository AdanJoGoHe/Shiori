import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastmcp import Client

from second_brain.backup import backup, restore
from second_brain.core import Brain, load_config
from second_brain.journal import read_journal
from second_brain.quality import classify_capture
from second_brain.server import create_server
from second_brain.viewer import ViewerServer, markdown_body
from second_brain.workflow import JournalConflict, overview, resume_project, snapshot, timeline
from test_core import brain as brain, event, journal_event


def task(version=0, status="open", **changes):
    return dict(
        id="editor-check",
        title="Probar el editor",
        details="Usar datos ficticios",
        status=status,
        version=version,
        **changes,
    )


def capture(**changes):
    return journal_event(project="demo", activity="parser", **changes)


def test_task_lifecycle_versions_tied_times_and_resume(brain, monkeypatch):
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-10-28T12:00:00+01:00"))
    brain.capture(
        capture(
            event_id="z-first",
            tasks=[task()],
            progress={"next_steps": ["Probar el editor"], "checks": ["3 pruebas pasaron"]},
        )
    )
    brain.capture(capture(event_id="a-second", tasks=[task(1, "blocked")]))
    current = snapshot(brain)["tasks"][("demo", "editor-check")]
    assert current["version"] == 2 and current["status"] == "blocked"
    assert [row["event_id"] for row in current["history"]] == ["z-first", "a-second"]
    pack = resume_project(brain, "demo")
    assert pack["active_tasks"][0]["version"] == 2
    assert pack["latest"]["event_id"] == "z-first"
    assert pack["suggested_next_steps"] == ["Probar el editor"]
    for version, status in [(2, "done"), (3, "open"), (4, "discarded")]:
        brain.capture(capture(event_id=f"transition-{version}", tasks=[task(version, status)]))
    assert resume_project(brain, "demo")["active_total"] == 0
    row = overview(brain, "demo")["tasks"][0]
    assert row["version"] == 5 and len(row["history"]) == 5


def test_task_scope_and_project_separation(brain):
    brain.capture(capture(tasks=[task()]))
    brain.capture(dict(capture(event_id="other"), project="other", tasks=[task(status="done")]))
    assert resume_project(brain, "demo")["active_total"] == 1
    assert resume_project(brain, "other")["active_total"] == 0
    assert resume_project(brain, "unknown")["latest"] is None
    with pytest.raises(ValueError):
        brain.capture(dict(capture(event_id="wrong"), scope="work"))


def test_concurrent_stale_updates_and_exact_retry(brain):
    brain.capture(capture(tasks=[task()]))

    def update(index):
        candidate = capture(event_id=f"update-{index}", tasks=[task(1, "done")])
        try:
            return brain.capture(candidate), candidate
        except JournalConflict:
            return None, candidate

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, range(2)))
    successes = [(result, candidate) for result, candidate in results if result]
    assert len(successes) == 1
    assert brain.capture(successes[0][1])["status"] == "duplicate"
    before = brain.ledger_path.read_bytes()
    stale = capture(event_id="stale", tasks=[task(1)])
    assert (
        classify_capture(
            brain,
            stale,
            dict(material="personal", reusable=False, meaningful=True, evidence_kind="observed"),
        )["decision"]
        == "deny"
    )
    with pytest.raises(JournalConflict):
        brain.capture(stale)
    assert brain.ledger_path.read_bytes() == before


def test_correction_grouping_dedup_and_preserved_task_history(brain):
    original = capture(summary="Primer resultado", tasks=[task()])
    saved = brain.capture(original)
    old = brain.path(saved["journal"]).read_text(encoding="utf-8")
    correction = capture(
        event_id="correction",
        summary="Resultado corregido",
        supersedes=[original["event_id"]],
        change_reason="Corregida la comprobación",
    )
    brain.capture(correction)
    state = snapshot(brain)
    assert state["superseded"][original["event_id"]] == "correction"
    assert state["tasks"][("demo", "editor-check")]["status"] == "open"
    assert brain.path(saved["journal"]).read_text(encoding="utf-8").startswith(old)
    assert resume_project(brain, "demo")["latest"]["summary"] == "Resultado corregido"
    # An unchanged activity is skipped, without allocating its new event ID.
    unchanged = capture(event_id="unchanged", summary="Resultado corregido")
    assert brain.capture(unchanged)["reason"] == "unchanged-activity"
    assert "unchanged" not in brain.ledger()["events"]
    assert (
        classify_capture(
            brain,
            unchanged,
            dict(material="personal", reusable=False, meaningful=True, evidence_kind="observed"),
        )["reason"]
        == "unchanged-activity"
    )
    with pytest.raises(JournalConflict):
        brain.capture(dict(correction, event_id="fork"))
    with pytest.raises(JournalConflict):
        brain.capture(
            dict(correction, event_id="cross-project", project="other", supersedes=["correction"])
        )
    rows = timeline(brain)["items"]
    assert (
        next(row for row in rows if row["event_id"] == original["event_id"])["superseded_by"]
        == "correction"
    )
    assert "shiori-data:" not in markdown_body(
        brain.path(saved["journal"]).read_text(encoding="utf-8")
    )


def test_repeated_activity_next_day_and_changed_note_are_not_skipped(brain, monkeypatch):
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-10-27T23:59:00+01:00"))
    brain.capture(capture())
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-10-28T00:01:00+01:00"))
    assert brain.capture(capture(event_id="next-day"))["status"] == "saved"
    brain.capture(event(project="demo", activity="parser"))
    assert (
        brain.capture(
            event(
                event_id="updated-note",
                project="demo",
                activity="parser",
                body="New verified observation",
            )
        )["status"]
        == "saved"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"tasks": "invalid"},
        {"tasks": [task()] * 2},
        {"tasks": [dict(task(), version=True)]},
        {"tasks": [dict(task(), id="../outside")]},
        {"tasks": [dict(task(), status="made-up")]},
        {"tasks": [dict(task(), details="password=synthetic-secret")]},
        {"tasks": [dict(task(), details="<!-- shiori-data:injected -->")]},
        {"activity": "../outside"},
        {"supersedes": ["journal-event"], "change_reason": "self"},
        {"supersedes": ["missing"]},
        {"project": None, "tasks": [task()]},
    ],
)
def test_invalid_tracking_never_writes(brain, changes):
    with pytest.raises(ValueError):
        brain.capture(dict(capture(), **changes))
    assert not brain.ledger_path.exists()


def test_interruption_fences_tracking_and_retry_keeps_original_day(brain, monkeypatch):
    import second_brain.core as core

    moment = datetime.fromisoformat("2026-10-27T23:59:00+01:00")
    monkeypatch.setattr(brain, "now", lambda: moment)
    original = core.atomic_write

    def fail_commit(path, content):
        if (
            path == brain.ledger_path
            and json.loads(content)["events"]["journal-event"]["status"] == "committed"
        ):
            raise OSError("Synthetic interruption")
        original(path, content)

    monkeypatch.setattr(core, "atomic_write", fail_commit)
    candidate = capture(tasks=[task()])
    with pytest.raises(OSError):
        brain.capture(candidate)
    assert resume_project(brain, "demo")["active_total"] == 0
    monkeypatch.setattr(core, "atomic_write", original)
    with pytest.raises(JournalConflict, match="Pending"):
        brain.capture(capture(event_id="overtake", tasks=[task()]))
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-10-28T00:01:00+01:00"))
    assert brain.capture(candidate)["journal"].endswith("2026-10-27.md")
    assert resume_project(brain, "demo")["active_tasks"][0]["version"] == 1


def test_old_tasks_survive_date_filters_and_backup(brain, monkeypatch, tmp_path):
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-01-01T12:00:00+01:00"))
    brain.capture(capture(tasks=[task()]))
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-10-28T12:00:00+01:00"))
    assert timeline(brain)["total"] == 0
    assert resume_project(brain, "demo")["active_total"] == 1
    backup(brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    recovered = Brain(load_config(tmp_path / "restored/config.json"))
    assert (
        resume_project(recovered, "demo")["active_tasks"]
        == resume_project(brain, "demo")["active_tasks"]
    )
    recovered.pause(False)
    recovered.capture(capture(event_id="restored-done", tasks=[task(1, "done")]))
    assert resume_project(recovered, "demo")["active_total"] == 0


def test_budgets_partial_history_and_legacy(brain, monkeypatch):
    saved = brain.capture(capture(tasks=[task()]))
    for index in range(12):
        brain.capture(
            capture(
                event_id=f"many-{index}",
                tasks=[dict(task(), id=f"task-{index}", details="x" * 500)],
            )
        )
    pack = resume_project(brain, "demo", 2000)
    assert len(json.dumps(pack, ensure_ascii=False)) <= 2000
    assert pack["tasks_omitted"] > 0 and pack["active_tasks"]
    board = overview(brain, "demo", max_chars=2000)
    assert len(json.dumps(board, ensure_ascii=False)) <= 2000 and board["next_offset"] is not None
    before = brain.ledger_path.read_bytes()
    brain.path(saved["journal"]).unlink()
    assert resume_project(brain, "demo")["error_count"]
    with pytest.raises(JournalConflict):
        brain.capture(capture(event_id="incomplete", tasks=[task()]))
    assert brain.ledger_path.read_bytes() == before


def test_viewer_http_journal_security_and_project_resume(brain):
    brain.capture(capture(tasks=[task()]))
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            assert (
                json.load(urlopen(server.url + "api/project-resume?project=demo"))["active_total"]
                == 1
            )
            assert (
                json.load(urlopen(server.url + "api/journal-state?project=demo"))["tasks"][0][
                    "version"
                ]
                == 1
            )
            candidate = capture(
                event_id="viewer-update", source_agent="manual", tasks=[task(1, "done")]
            )

            def post(payload, origin):
                return urlopen(
                    Request(
                        server.url + "api/journal",
                        data=json.dumps(payload).encode(),
                        headers={"Content-Type": "application/json", "Origin": origin},
                        method="POST",
                    )
                )

            with pytest.raises(HTTPError) as denied:
                post(candidate, "http://untrusted.invalid")
            assert denied.value.code == 403
            with pytest.raises(HTTPError) as denied:
                post(event(source_agent="manual"), server.origin)
            assert denied.value.code == 400
            assert json.load(post(candidate, server.origin))["status"] == "saved"
            assert json.load(post(candidate, server.origin))["status"] == "duplicate"
            with pytest.raises(HTTPError) as conflict:
                post(dict(candidate, event_id="stale-update"), server.origin)
            assert conflict.value.code == 409
            with pytest.raises(HTTPError):
                urlopen(server.url + "api/journal?project=demo&project=other")
        finally:
            server.shutdown()
            thread.join(5)


def test_stdio_resume_and_classification_preserve_tracking(brain):
    async def scenario():
        async with Client(create_server(brain.config)) as client:
            result = await client.call_tool(
                "classify_memory",
                {
                    "candidate": capture(tasks=[task()]),
                    "assessment": dict(
                        material="personal",
                        reusable=False,
                        meaningful=True,
                        evidence_kind="observed",
                    ),
                },
            )
            assert result.data["candidate"]["tasks"] == [task()]
            await client.call_tool("capture_memory", {"candidate": result.data["candidate"]})
            result = await client.call_tool("resume_project", {"project": "demo"})
            tasks = await client.call_tool("read_journal", {"project": "demo", "view": "tasks"})
            assert tasks.data["tasks"][0]["history_total"] == 1
            assert (
                result.data["scope"] == "personal"
                and result.data["active_tasks"][0]["version"] == 1
            )

    asyncio.run(scenario())


def test_legacy_progress_and_structured_heading_text(brain):
    saved = brain.capture(capture(progress={"next_steps": ["Revisar el lector"]}))
    path = brain.path(saved["journal"])
    path.write_text(
        "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("<!-- shiori-data:")
        )
        + "\n",
        encoding="utf-8",
    )
    assert resume_project(brain, "demo")["suggested_next_steps"] == ["Revisar el lector"]
    brain.capture(
        capture(event_id="headings", summary="A literal heading:\n### Checks\n- " + "x" * 600)
    )
    assert not snapshot(brain)["errors"]


def test_timeline_task_pages_and_closed_state_query(brain):
    for index in range(24):
        brain.capture(
            capture(
                event_id=f"page-{index}",
                summary=f"Result {index}",
                tasks=[dict(task(), id=f"task-{index}", status="done", details="d" * 500)],
            )
        )
    rows, offset = [], 0
    while True:
        page = timeline(brain, project="demo", offset=offset)
        rows.extend(row["event_id"] for row in page["items"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert len(set(rows)) == len(rows) == 24
    offset, ids = 0, []
    while True:
        page = read_journal(brain, project="demo", offset=offset, max_chars=2000, view="tasks")
        assert len(json.dumps(page, ensure_ascii=False)) <= 2000
        ids.extend(row["id"] for row in page["tasks"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert len(set(ids)) == len(ids) == 24
    assert resume_project(brain, "demo")["active_total"] == 0
    with pytest.raises(ValueError):
        read_journal(brain, view="tasks", project="demo", start_date="2026-10-01")


def test_history_scan_limit_blocks_mutation_without_hiding_incompleteness(brain, monkeypatch):
    import second_brain.journal as journal

    brain.capture(capture(tasks=[task()]))
    monkeypatch.setattr(journal, "MAX_SCAN_BYTES", 1)
    assert resume_project(brain, "demo")["error_count"] > 0
    before = brain.ledger_path.read_bytes()
    with pytest.raises(JournalConflict):
        brain.capture(capture(event_id="limited", tasks=[task(1, "done")]))
    assert brain.ledger_path.read_bytes() == before


def test_resume_escaping_budget_and_strict_timeline_dates(brain):
    brain.capture(dict(capture(), title='"' * 200, summary='"' * 1000))
    result = resume_project(brain, "demo", max_chars=2000)
    assert len(json.dumps(result, ensure_ascii=False)) <= 2000 and result["truncated"]
    with pytest.raises(ValueError):
        timeline(brain, start_date="2026-W44-3")
