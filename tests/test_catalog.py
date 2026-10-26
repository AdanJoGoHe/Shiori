import json
import os
import subprocess
from pathlib import Path

import pytest

from second_brain.catalog import Catalog
from second_brain.core import Brain


@pytest.fixture
def catalog(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    brain = Brain(
        {
            "scope": "personal",
            "vault_path": str(tmp_path / "vault"),
            "state_path": str(tmp_path / "state"),
            "timezone": "Europe/Madrid",
            "documentation_roots": {"project-docs": str(docs)},
        }
    )
    brain.capture(
        {
            "scope": "personal",
            "id": "example",
            "event_id": "example-event",
            "title": "Synthetic note",
            "type": "knowledge",
            "status": "verified",
            "source_agent": "codex",
            "body": "Synthetic knowledge",
            "evidence": "Test",
            "tags": ["python"],
            "project": "example",
        }
    )
    (docs / "guide.md").write_text(
        "# Synthetic guide\n\nBody is not catalog metadata.", encoding="utf-8"
    )
    return Catalog(brain)


def test_catalog_separates_sources_paginates_and_preserves_files(catalog):
    roots = [
        catalog.brain.vault,
        catalog.brain.state,
        Path(catalog.brain.config["documentation_roots"]["project-docs"]),
    ]
    before = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
    first = catalog.list(limit=2)
    assert len(first["items"]) == 2 and first["next_offset"] == 2
    second = catalog.list(offset=2, limit=2)
    assert len(second["items"]) == 1 and second["next_offset"] is None
    rows = first["items"] + second["items"]
    assert {r["kind"] for r in rows} == {"documentation", "note", "journal"}
    assert len({r["id"] for r in rows}) == 3
    note = next(r for r in rows if r["kind"] == "note")
    assert note["metadata"]["tags"] == ["python"]
    assert note["metadata"]["status"] == "verified"
    doc = next(r for r in rows if r["kind"] == "documentation")
    assert doc["title"] == "Synthetic guide"
    assert doc["metadata"]["tags"] is None and doc["metadata"]["status"] is None
    assert "Body is not" not in json.dumps(rows)
    assert catalog.list(kind="journal")["items"][0]["metadata"]["status"] is None
    assert catalog.list(source="project-docs")["items"] == [doc]
    after = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
    assert before == after


def test_catalog_refreshes_and_skips_unmanaged_and_excluded_content(catalog):
    docs = Path(catalog.brain.config["documentation_roots"]["project-docs"])
    for relative in [
        ".git/private.md",
        "archive/old.md",
        "local/private.md",
        "runtime/private.md",
        "backups/private.md",
        "credentials.md",
        "notes.txt",
    ]:
        path = docs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Do not list", encoding="utf-8")
    catalog.brain.path("knowledge/unmanaged.md").write_text("# Unmanaged", encoding="utf-8")
    catalog.brain.path("journal/not-a-day.md").write_text("# Unmanaged journal", encoding="utf-8")
    rows = catalog.list()["items"]
    assert len(rows) == 3
    guide_id = next(r["id"] for r in rows if r["kind"] == "documentation")
    (docs / "guide.md").write_text("# Renamed heading", encoding="utf-8")
    assert catalog.list(kind="documentation")["items"][0]["id"] == guide_id
    assert catalog.list(kind="documentation")["items"][0]["title"] == "Renamed heading"
    (docs / "guide.md").unlink()
    assert catalog.list(kind="documentation")["items"] == []
    assert catalog.brain.search("Unmanaged") == []


def test_catalog_source_failure_is_partial_and_redacted(catalog, tmp_path):
    catalog.brain.config["documentation_roots"]["missing"] = str(tmp_path / "does-not-exist")
    docs = Path(catalog.brain.config["documentation_roots"]["project-docs"])
    (docs / "bad.md").write_bytes(b"\xff")
    (docs / "secret.md").write_text("# password=synthetic-secret", encoding="utf-8")
    result = catalog.list()
    assert len(result["items"]) == 3
    assert {e["code"] for e in result["errors"]} >= {"unavailable", "invalid-content"}
    assert str(tmp_path) not in json.dumps(result)
    assert "synthetic-secret" not in json.dumps(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "work"},
        {"source": "../outside"},
        {"source": "unknown"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_catalog_rejects_invalid_requests(catalog, changes):
    with pytest.raises(ValueError):
        catalog.list(**changes)


def test_catalog_rejects_documentation_roots_overlapping_private_state(catalog):
    for path in [catalog.brain.state, catalog.brain.vault, catalog.brain.vault.parent]:
        catalog.brain.config["documentation_roots"] = {"unsafe": str(path)}
        result = catalog.list(kind="documentation")
        assert result["items"] == []
        assert result["errors"][0]["code"] == "invalid-root"


def test_catalog_scan_limit_is_reported(catalog, monkeypatch):
    docs = Path(catalog.brain.config["documentation_roots"]["project-docs"])
    (docs / "second.md").write_text("# Second", encoding="utf-8")
    monkeypatch.setattr(catalog, "MAX_ENTRIES", 1)
    result = catalog.list(kind="documentation")
    assert result["truncated"] is True
    assert any(e["code"] == "scan-limit" for e in result["errors"])


def test_catalog_health_distinguishes_empty_partial_unavailable_and_limit(catalog, tmp_path):
    docs = Path(catalog.brain.config["documentation_roots"]["project-docs"])
    (docs / "guide.md").unlink()
    assert catalog.snapshot(kind="documentation")["diagnostics"]["status"] == "empty"
    (docs / "bad.md").write_bytes(b"\xff")
    failed = catalog.snapshot(kind="documentation")["diagnostics"]
    assert failed["status"] == "unavailable"
    assert failed["codes"] == ["invalid-content"]
    assert failed["catalog_items"] == 0
    assert catalog.snapshot()["diagnostics"]["status"] == "partial"
    empty = tmp_path / "empty"
    empty.mkdir()
    catalog.brain.config["documentation_roots"]["empty"] = str(empty)
    assert catalog.snapshot(kind="documentation")["diagnostics"]["status"] == "partial"
    catalog.MAX_ENTRIES = 0
    limited = catalog.snapshot()["diagnostics"]
    assert limited["status"] == "limited"
    assert "scan-limit" in limited["codes"]


def test_note_catalog_disagreement_is_counted_without_private_errors(catalog):
    catalog.brain.path(catalog.brain.ledger()["notes"]["example"]).write_bytes(b"\xff")
    diagnosis = catalog.snapshot(kind="note")["diagnostics"]
    assert diagnosis["status"] == "unavailable"
    assert diagnosis["registered_notes"] == 1
    assert diagnosis["readable_notes"] == 0
    assert "ledger-catalog-mismatch" in diagnosis["codes"]
    assert str(catalog.brain.vault) not in json.dumps(diagnosis)


@pytest.mark.parametrize("relative", ["", ".", None, 1])
def test_invalid_registered_path_is_a_read_failure(catalog, relative):
    ledger = catalog.brain.ledger()
    ledger["notes"]["example"] = relative
    catalog.brain.ledger_path.write_text(json.dumps(ledger))
    result = catalog.snapshot(kind="note")
    assert result["diagnostics"]["status"] == "unavailable"
    assert result["diagnostics"]["registered_notes"] == 1
    assert result["diagnostics"]["readable_notes"] == 0


def test_root_becoming_unavailable_still_returns_safe_diagnostics(catalog, monkeypatch):
    original = Path.resolve

    def unavailable(path, *args, **kwargs):
        if path == catalog.brain.vault:
            raise OSError("Synthetic private root")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", unavailable)
    diagnosis = catalog.snapshot(kind="note")["diagnostics"]
    assert diagnosis["status"] == "unavailable" and diagnosis["store_id"] is None
    assert "Synthetic private root" not in json.dumps(diagnosis)


def test_catalog_windows_junction_is_not_followed(catalog, tmp_path):
    if os.name != "nt":
        pytest.skip("Windows-only junction check")
    docs = Path(catalog.brain.config["documentation_roots"]["project-docs"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.md").write_text("# Outside", encoding="utf-8")
    linked = docs / "linked"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(linked), str(outside)], capture_output=True
    )
    if result.returncode:
        pytest.skip("Junction creation unavailable")
    try:
        result = catalog.list(kind="documentation")
        assert [r["title"] for r in result["items"]] == ["Synthetic guide"]
        assert any(e["code"] == "linked-path" for e in result["errors"])
        catalog.brain.config["documentation_roots"] = {"linked": str(linked)}
        assert catalog.list(kind="documentation")["errors"][0]["code"] == "invalid-root"
    finally:
        os.rmdir(linked)
