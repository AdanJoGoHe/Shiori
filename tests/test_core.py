import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from second_brain.core import Brain


@pytest.fixture
def brain(tmp_path):
    return Brain(
        {
            "scope": "personal",
            "vault_path": str(tmp_path / "vault"),
            "state_path": str(tmp_path / "state"),
            "timezone": "Europe/Madrid",
        }
    )


def event(**changes):
    return {
        "scope": "personal",
        "id": "git-version",
        "event_id": "test-event",
        "title": "Git version",
        "type": "command",
        "status": "verified",
        "source_agent": "codex",
        "body": "Run git --version. Requires Git on PATH.",
        "evidence": "Observed successful execution",
        **changes,
    }


def test_capture_retrieve_duplicate_and_revision(brain):
    result = brain.capture(event())
    assert result["status"] == "saved"
    assert brain.capture(event())["status"] == "duplicate"
    assert brain.search("git")[0]["id"] == "git-version"
    assert "git --version" in brain.read("git-version")
    brain.capture(event(event_id="updated", body="A corrected command."))
    assert "corrected" in brain.read("git-version")
    assert len(list((brain.vault / "archive/git-version").glob("*.md"))) == 1
    journal = brain.path(result["journal"]).read_text(encoding="utf-8")
    assert journal.count("<!-- event:test-event -->") == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "work"},
        {"id": "../escape"},
        {"id": "C:/escape"},
        {"status": "made-up"},
        {"type": "raw-transcript"},
        {"evidence": ""},
        {"body": "password=supersecret123"},
        {"body": "Authorization: Bearer xyz"},
        {"body": "-----BEGIN PRIVATE KEY-----"},
        {"body": "x" * 20001},
        {"extra": "api_key=secret123"},
        {"source_agent": "other"},
    ],
)
def test_invalid_or_sensitive_inputs_rejected(brain, changes):
    with pytest.raises(ValueError):
        brain.capture(event(**changes))
    assert brain.status()["notes"] == 0
    assert list(brain.vault.rglob("*.md")) == []


def test_pause_preserves_retrieval(brain):
    brain.capture(event())
    brain.pause(True)
    assert brain.capture(event(event_id="paused"))["reason"] == "paused"
    assert brain.search("git")
    brain.pause(False)
    assert brain.capture(event(event_id="resumed"))["status"] == "saved"


def test_concurrent_journal_writes(brain):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda i: brain.capture(event(id=f"note-{i}", event_id=f"event-{i}")), range(8)
            )
        )
    assert brain.status()["notes"] == 8
    journal = brain.path(results[0]["journal"]).read_text(encoding="utf-8")
    assert journal.count("<!-- event:") == 8


def test_reused_event_with_changed_payload_rejected(brain):
    brain.capture(event())
    with pytest.raises(ValueError, match="reused"):
        brain.capture(event(body="Different"))


def test_partial_write_retry(brain, monkeypatch):
    import second_brain.core as core

    original = core.atomic_write

    def fail_journal(path, content):
        if "journal" in path.parts:
            raise OSError("Synthetic disk error")
        original(path, content)

    monkeypatch.setattr(core, "atomic_write", fail_journal)
    with pytest.raises(OSError):
        brain.capture(event())
    assert brain.status()["pending"] == 1
    monkeypatch.setattr(core, "atomic_write", original)
    assert brain.capture(event())["status"] == "saved"
    assert brain.status()["pending"] == 0


def test_path_traversal_and_symlink(brain, tmp_path):
    with pytest.raises(ValueError):
        brain.path("../outside.md")
    try:
        (brain.vault / "knowledge").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError):
        brain.capture(event(type="knowledge"))


def test_read_rejects_tampered_scope(brain):
    result = brain.capture(event())
    path = brain.path(result["path"])
    path.write_text(
        path.read_text(encoding="utf-8").replace("scope: personal", "scope: work"), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        brain.read("git-version")


def test_work_deployment_denied(tmp_path):
    with pytest.raises(ValueError):
        Brain({"scope": "work"})


@pytest.mark.parametrize("journal_only", [False, True])
def test_windows_junction_escape_denied(brain, tmp_path, journal_only):
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows-only junction check")
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = brain.vault / ("journal" if journal_only else "knowledge")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(linked), str(outside)], capture_output=True
    )
    if result.returncode:
        pytest.skip("Junction creation unavailable")
    try:
        with pytest.raises(ValueError, match="Linked"):
            brain.capture(journal_event() if journal_only else event(type="knowledge"))
        assert list(outside.iterdir()) == []
    finally:
        os.rmdir(linked)


def test_ledger_contains_no_note_body(brain):
    brain.capture(event())
    ledger = json.loads(brain.ledger_path.read_text())
    assert "Run git" not in str(ledger)


def test_metadata_round_trip_preserved_and_explicitly_cleared(brain):
    import yaml

    brain.capture(
        event(
            tags=[" Python ", "PYTHON", "windows"],
            project="second-brain",
            source_refs=["docs/example.md"],
            related=["other-note"],
            sensitivity="private",
        )
    )
    metadata = yaml.safe_load(brain.read("git-version").split("---", 2)[1])
    assert metadata["tags"] == ["python", "windows"]
    assert metadata["project"] == "second-brain"
    assert metadata["source_refs"] == ["docs/example.md"]
    assert metadata["related"] == ["other-note"]
    assert metadata["sensitivity"] == "private"
    brain.capture(event(event_id="metadata-preserved", body="Updated body"))
    preserved = yaml.safe_load(brain.read("git-version").split("---", 2)[1])
    for key in ["tags", "project", "source_refs", "related", "sensitivity"]:
        assert preserved[key] == metadata[key]
    brain.capture(
        event(event_id="metadata-cleared", tags=[], project=None, related=[], source_refs=[])
    )
    cleared = yaml.safe_load(brain.read("git-version").split("---", 2)[1])
    assert cleared["tags"] == cleared["source_refs"] == cleared["related"] == []
    assert cleared["project"] is None
    assert len(list((brain.vault / "archive/git-version").glob("*.md"))) == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {"tags": "python"},
        {"tags": [None]},
        {"tags": [" "]},
        {"tags": ["x"] * 21},
        {"project": []},
        {"project": "../escape"},
        {"related": ["../outside"]},
        {"source_refs": [42]},
        {"source_refs": ["password=synthetic-secret"]},
        {"sensitivity": "public"},
    ],
)
def test_invalid_metadata_rejected_before_writing(brain, metadata):
    with pytest.raises(ValueError):
        brain.capture(event(**metadata))
    assert not brain.ledger_path.exists()
    assert not list(brain.vault.rglob("*.md"))


def test_search_combines_exact_metadata_filters(brain):
    brain.capture(event(tags=["Python", "windows"], project="one"))
    brain.capture(event(id="other", event_id="other", tags=["python"], project="two"))
    assert [
        x["id"]
        for x in brain.search("git", filters={"tags": ["PYTHON", "windows"], "project": "one"})
    ] == ["git-version"]
    assert brain.search("git", filters={"tags": ["win"]}) == []
    assert brain.search("git", filters={"project": "missing"}) == []
    assert [
        x["id"]
        for x in brain.search(
            "",
            filters={
                "project": "two",
                "type": "command",
                "status": "verified",
                "source_agent": "codex",
            },
        )
    ] == ["other"]
    brain.capture(event(id="untagged", event_id="untagged"))
    assert [x["id"] for x in brain.search("", filters={"project": None, "tags": []})] == [
        "untagged"
    ]


@pytest.mark.parametrize(
    "filters",
    [
        {"scope": "work"},
        {"tags": "python"},
        {"status": "unknown"},
        {"type": "unknown"},
        {"source_agent": "unknown"},
        {"project": "../escape"},
    ],
)
def test_invalid_search_filters_rejected(brain, filters):
    with pytest.raises(ValueError):
        brain.search("git", filters=filters)


def test_read_rejects_tampered_metadata(brain):
    saved = brain.capture(event())
    path = brain.path(saved["path"])
    path.write_text(
        path.read_text(encoding="utf-8").replace("tags: []", "tags: invalid"), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        brain.read("git-version")


def journal_event(**changes):
    return {
        "scope": "personal",
        "mode": "journal-only",
        "event_id": "journal-event",
        "title": "Synthetic task completed",
        "source_agent": "codex",
        "summary": "Validated a synthetic build; no reusable lesson.",
        **changes,
    }


def test_journal_only_preserves_notes_and_deduplicates(brain):
    note = brain.capture(event())
    before = brain.path(note["path"]).read_bytes()
    saved = brain.capture(journal_event())
    assert saved == {"status": "saved", "journal": note["journal"]}
    assert brain.capture(journal_event()) == {"status": "duplicate", "journal": note["journal"]}
    journal = brain.path(saved["journal"]).read_text(encoding="utf-8")
    assert journal.count("<!-- event:journal-event -->") == 1
    assert journal.count("- Knowledge:") == 1  # Only the note capture has a canonical link.
    assert "no reusable lesson" in journal
    assert brain.path(note["path"]).read_bytes() == before
    assert brain.status()["notes"] == 1
    assert brain.search("synthetic") == []
    assert not (brain.vault / "archive").exists()
    assert "no reusable lesson" not in brain.ledger_path.read_text()


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "work"},
        {"mode": "unknown"},
        {"event_id": "../escape"},
        {"source_agent": "unknown"},
        {"summary": ""},
        {"summary": "x" * 1001},
        {"summary": "password=synthetic-secret"},
        {"title": "Authorization: Bearer synthetic"},
        {"id": "accidental-note"},
        {"extra": "api_key=synthetic-secret"},
    ],
)
def test_invalid_journal_only_leaves_no_writes(brain, changes):
    with pytest.raises(ValueError):
        brain.capture(journal_event(**changes))
    assert not brain.ledger_path.exists()
    assert list(brain.vault.rglob("*.md")) == []


@pytest.mark.parametrize("failure", ["journal", "commit"])
def test_journal_only_retry_keeps_original_day(brain, monkeypatch, failure):
    from datetime import datetime

    import second_brain.core as core

    first_day = datetime.fromisoformat("2026-10-16T23:59:00+02:00")
    monkeypatch.setattr(brain, "now", lambda: first_day)
    original = core.atomic_write

    def fail_write(path, content):
        if failure == "journal" and "journal" in path.parts:
            raise OSError("Synthetic journal write failure")
        if failure == "commit" and path == brain.ledger_path:
            if json.loads(content)["events"]["journal-event"]["status"] == "committed":
                raise OSError("Synthetic ledger commit failure")
        original(path, content)

    monkeypatch.setattr(core, "atomic_write", fail_write)
    with pytest.raises(OSError, match="Synthetic"):
        brain.capture(journal_event())
    assert brain.status()["pending"] == 1
    monkeypatch.setattr(core, "atomic_write", original)
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-10-17T00:01:00+02:00"))
    saved = brain.capture(journal_event())
    assert saved["journal"] == "journal/2026/2026-10-16.md"
    assert brain.path(saved["journal"]).read_text().count("<!-- event:journal-event -->") == 1
    assert brain.status()["pending"] == 0
    assert brain.status()["notes"] == 0
    assert not brain.path("journal/2026/2026-10-17.md").exists()


def test_journal_only_pause_and_event_conflicts(brain):
    brain.pause(True)
    assert brain.capture(journal_event())["status"] == "skipped"
    assert list(brain.vault.rglob("*.md")) == []
    brain.pause(False)
    brain.capture(journal_event())
    with pytest.raises(ValueError, match="reused"):
        brain.capture(journal_event(summary="Changed outcome"))
    with pytest.raises(ValueError, match="reused"):
        brain.capture(event(event_id="journal-event"))


def test_concurrent_notes_and_journal_only(brain):
    candidates = [journal_event(event_id=f"journal-{i}") for i in range(4)]
    candidates += [event(id=f"note-{i}", event_id=f"note-event-{i}") for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(brain.capture, candidates))
    journal = brain.path(results[0]["journal"]).read_text(encoding="utf-8")
    assert journal.count("<!-- event:") == 8
    assert journal.count("- Knowledge:") == 4
    assert brain.status()["notes"] == 4
    assert brain.status()["pending"] == 0
