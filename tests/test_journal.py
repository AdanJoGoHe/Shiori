import asyncio
import json
import subprocess
import sys
from datetime import datetime

import pytest
from fastmcp import Client

from second_brain.backup import backup, restore
from second_brain.core import Brain, load_config
from second_brain.journal import read_journal
from second_brain.quality import classify_capture
from second_brain.server import create_server
from test_core import brain as brain, event, journal_event


def freeze(brain, monkeypatch, stamp="2026-10-27T18:30:00+01:00"):
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat(stamp))


def progress_event(**changes):
    return journal_event(
        project="synthetic",
        progress={
            "completed": ["Fixed the synthetic parser"],
            "checks": ["Focused tests: 3 passed"],
            "decisions": ["Keep the input format"],
            "blockers": ["Real host validation pending"],
            "next_steps": ["Try a synthetic example in the host"],
        },
        **changes,
    )


def test_structured_capture_classification_retry_and_resume(brain, monkeypatch):
    freeze(brain, monkeypatch)
    original = progress_event()
    classified = classify_capture(
        brain,
        original,
        dict(material="personal", reusable=False, meaningful=True, evidence_kind="observed"),
    )
    assert classified["candidate"] == original
    assert brain.capture(classified["candidate"])["status"] == "saved"
    before = brain.ledger_path.read_bytes()
    assert brain.capture(original)["status"] == "duplicate"
    brain.pause(True)
    result = read_journal(brain, project="synthetic")
    assert result["total"] == 1 and not result["errors"]
    item = result["items"][0]
    assert all(value[0] in item["content"] for value in original["progress"].values())
    assert "### Next Steps" in item["content"]
    assert brain.search("parser") == []
    assert brain.ledger_path.read_bytes() == before
    assert "Fixed the synthetic parser" not in before.decode()
    brain.pause(False)
    with pytest.raises(ValueError, match="reused"):
        brain.capture(dict(original, summary="Changed"))


@pytest.mark.parametrize(
    "fields",
    [
        {"progress": []},
        {"progress": {"made_up": []}},
        {"progress": {"checks": "test passed"}},
        {"progress": {"checks": [1]}},
        {"progress": {"checks": [" "]}},
        {"progress": {"checks": ["x"] * 9}},
        {"progress": {"checks": ["x" * 501]}},
        {"progress": {"checks": ["password=synthetic-secret"]}},
        {"progress": {"checks": ["<!-- event:fake -->"]}},
        {"summary": "<!-- shiori-project:other -->"},
        {"project": "../outside"},
    ],
)
def test_invalid_progress_does_not_write(brain, fields):
    with pytest.raises(ValueError):
        brain.capture(dict(progress_event(), **fields))
    assert not brain.ledger_path.exists()


def test_note_and_legacy_journals_with_project_filters(brain, monkeypatch):
    freeze(brain, monkeypatch)
    saved = brain.capture(event(project="synthetic"))
    brain.capture(event(event_id="update", progress={"checks": ["New check"]}))
    brain.capture(journal_event())
    path = brain.path(saved["journal"])
    text = path.read_text(encoding="utf-8")
    # The old six-field writer produced no project comment.
    path.write_text(text.replace("<!-- shiori-project: -->\n", ""), encoding="utf-8")
    all_rows = read_journal(brain)
    assert all_rows["total"] == 3
    filtered = read_journal(brain, project="synthetic")
    assert filtered["total"] == 2
    assert all(row["project"] == "synthetic" for row in filtered["items"])
    assert "New check" in next(
        row["content"] for row in filtered["items"] if row["event_id"] == "update"
    )
    assert read_journal(brain, project="another")["items"] == []


def test_local_dates_range_pagination_and_json_budget(brain, monkeypatch):
    freeze(brain, monkeypatch, "2026-10-26T23:59:00+01:00")
    brain.capture(progress_event(event_id="yesterday"))
    freeze(brain, monkeypatch)
    for index in range(5):
        brain.capture(
            dict(progress_event(event_id=f"today-{index}"), summary="Unicode: café. " * 60)
        )
    page = read_journal(brain, max_chars=2000)
    assert page["total"] == 6 and page["truncated"]
    ids = []
    offset = 0
    while True:
        page = read_journal(brain, offset=offset, max_chars=2000)
        assert len(json.dumps(page, ensure_ascii=False)) <= 2000
        ids.extend(item["event_id"] for item in page["items"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert len(set(ids)) == len(ids) == 6 and ids[-1] == "yesterday"
    assert read_journal(brain, start_date="2026-10-27")["total"] == 5
    assert read_journal(brain, end_date="2026-10-26")["total"] == 1
    small = read_journal(brain, max_chars=1000)
    assert len(json.dumps(small, ensure_ascii=False)) <= 1000
    assert small["items"] and small["items"][0]["content_truncated"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_date": "../outside"},
        {"start_date": "2026-02-30"},
        {"start_date": "20261027"},
        {"start_date": "2026-01-01", "end_date": "2026-02-01"},
        {"start_date": "2026-10-28", "end_date": "2026-10-27"},
        {"project": "../outside"},
        {"offset": -1},
        {"offset": True},
        {"max_chars": 999},
    ],
)
def test_invalid_queries(brain, kwargs):
    with pytest.raises(ValueError):
        read_journal(brain, **kwargs)


@pytest.mark.parametrize("damage", ["missing", "secret", "oversized", "marker", "duplicate"])
def test_unreadable_days_report_errors_without_exposing_content(brain, monkeypatch, damage):
    freeze(brain, monkeypatch)
    path = brain.path(brain.capture(progress_event())["journal"])
    text = path.read_text(encoding="utf-8")
    if damage == "missing":
        path.unlink()
    else:
        text = {
            "secret": "password=synthetic-private",
            "oversized": "x" * (2 * 1024 * 1024 + 1),
            "marker": text.replace("event:journal-event", "event:unknown"),
            "duplicate": text + text,
        }[damage]
        path.write_text(text, encoding="utf-8")
    result = read_journal(brain)
    assert result["items"] == [] and result["errors"]
    assert "synthetic-private" not in json.dumps(result)


def test_pending_entry_is_not_reported_as_completed(brain, monkeypatch):
    freeze(brain, monkeypatch)
    brain.capture(progress_event())
    ledger = brain.ledger()
    ledger["events"]["journal-event"]["status"] = "pending"
    brain.ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    assert read_journal(brain)["total"] == 0


def test_work_scope_cli_and_stdio_same_diary(tmp_path):
    config = dict(
        schema_version=1,
        scope="work",
        timezone="Europe/Madrid",
        vault_path=str(tmp_path / "vault"),
        state_path=str(tmp_path / "state"),
    )
    brain = Brain(config)
    candidate = dict(progress_event(), scope="work", source_agent="augment-jetbrains")

    async def scenario():
        async with Client(create_server(config)) as client:
            saved = await client.call_tool("capture_memory", {"candidate": candidate})
            assert saved.data["status"] == "saved"
            found = await client.call_tool("read_journal", {"project": "synthetic"})
            assert found.data["scope"] == "work" and found.data["total"] == 1
            return found.data

    observed = asyncio.run(scenario())
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "second_brain.cli",
            "--config",
            str(path),
            "journal",
            "--project",
            "synthetic",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert json.loads(cli.stdout) == observed
    assert brain.status()["notes"] == 0


def test_progress_survives_backup_restore(brain, tmp_path, monkeypatch):
    freeze(brain, monkeypatch)
    brain.capture(progress_event())
    bundle = tmp_path / "bundle"
    backup(brain, bundle)
    restore(bundle, tmp_path / "restored")
    restored_brain = Brain(load_config(tmp_path / "restored/config.json"))
    result = read_journal(restored_brain, end_date="2026-10-27", project="synthetic")
    assert result["total"] == 1 and not result["errors"]
    assert "Real host validation pending" in result["items"][0]["content"]
