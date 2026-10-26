import json
import os
import subprocess
import sys
from pathlib import Path


def test_catalog_doctor_is_read_only_redacted_and_reports_mismatch(tmp_path):
    from second_brain.core import Brain
    from test_core import event

    config = tmp_path / "selected.json"
    settings = {
        "schema_version": 1,
        "scope": "personal",
        "timezone": "Europe/Madrid",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
    }
    config.write_text(json.dumps(settings))
    command = [
        sys.executable,
        "-m",
        "second_brain.cli",
        "--config",
        str(config),
        "doctor",
        "--catalog",
    ]
    absent = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=15)
    assert absent.returncode == 1 and not absent.stderr
    assert json.loads(absent.stdout)["status"] == "unavailable"
    assert not Path(settings["vault_path"]).exists() and not Path(settings["state_path"]).exists()
    brain = Brain(settings)
    brain.capture(event())
    brain.path(brain.ledger()["notes"]["git-version"]).write_bytes(b"\xff synthetic-private-detail")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    failure = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=15)
    assert failure.returncode == 1 and not failure.stderr
    result = json.loads(failure.stdout)
    assert result["status"] == "partial"
    assert result["catalog"]["registered_notes"] == 1
    assert result["catalog"]["readable_notes"] == 0
    assert "ledger-catalog-mismatch" in result["catalog"]["codes"]
    assert result["paths"]["roots"]["vault_path"]["root_id"]
    assert str(tmp_path) not in failure.stdout and "synthetic-private-detail" not in failure.stdout
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_doctor_provider_is_opt_in_and_failure_is_machine_readable(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "personal",
                "vault_path": str(tmp_path / "vault"),
                "state_path": str(tmp_path / "state"),
                "timezone": "Europe/Madrid",
            }
        )
    )
    command = [sys.executable, "-m", "second_brain.cli", "--config", str(config), "doctor"]
    default = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert default.returncode == 0
    assert "provider_check" not in json.loads(default.stdout)
    explicit = subprocess.run(command + ["--provider"], capture_output=True, text=True, timeout=15)
    assert explicit.returncode == 1 and explicit.stderr == ""
    result = json.loads(explicit.stdout)
    assert result["note_validation"] == "passed"
    assert result["provider_check"] == {
        "status": "unavailable",
        "check": "project-status",
        "reason": "not-configured",
    }


def test_cli_journal_only_with_isolated_deployment(tmp_path):
    config = {
        "schema_version": 1,
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    event_file = tmp_path / "event.json"
    candidate = {
        "scope": "personal",
        "mode": "journal-only",
        "event_id": "synthetic-cli-journal",
        "title": "Synthetic CLI progress",
        "source_agent": "codex",
        "summary": "Completed synthetic CLI acceptance.",
    }
    event_file.write_text(json.dumps(candidate), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "second_brain.cli",
        "--config",
        str(config_file),
        "capture",
        "--event-file",
        str(event_file),
    ]
    for expected in ["saved", "duplicate"]:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == expected
    journal = (Path(config["vault_path"]) / payload["journal"]).read_text(encoding="utf-8")
    assert journal.count("<!-- event:synthetic-cli-journal -->") == 1
    ledger = json.loads((Path(config["state_path"]) / "ledger.json").read_text())
    assert ledger["notes"] == {}
    candidate["summary"] = "password=synthetic-secret"
    event_file.write_text(json.dumps(candidate), encoding="utf-8")
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert rejected.returncode == 1
    assert (Path(config["vault_path"]) / payload["journal"]).read_text(encoding="utf-8") == journal


def test_cli_capture_and_metadata_search(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Synthetic CLI guide — guía", encoding="utf-8")
    config = {
        "schema_version": 1,
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    config_file = tmp_path / "config.json"
    config["documentation_roots"] = {"project-docs": str(docs)}
    config_file.write_text(json.dumps(config), encoding="utf-8")
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(
            {
                "scope": "personal",
                "id": "example",
                "event_id": "example-event",
                "title": "Synthetic CLI metadata",
                "type": "knowledge",
                "status": "verified",
                "source_agent": "codex",
                "body": "Synthetic content",
                "evidence": "Synthetic test",
                "project": "one",
                "tags": ["python", "windows"],
            }
        ),
        encoding="utf-8",
    )
    command = [sys.executable, "-m", "second_brain.cli", "--config", str(config_file)]
    subprocess.run(
        command + ["capture", "--event-file", str(event_file)], check=True, capture_output=True
    )
    for project, expected in [("one", ["example"]), ("two", [])]:
        result = subprocess.run(
            command
            + [
                "search",
                "synthetic",
                "--project",
                project,
                "--tag",
                "PYTHON",
                "--tag",
                "windows",
                "--type",
                "knowledge",
                "--status",
                "verified",
                "--source-agent",
                "codex",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert [n["id"] for n in json.loads(result.stdout)] == expected
    catalog = subprocess.run(
        command
        + ["catalog", "--kind", "documentation", "--source", "project-docs", "--limit", "1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),
        timeout=15,
    )
    assert catalog.returncode == 0, catalog.stderr
    rows = json.loads(catalog.stdout)["items"]
    assert len(rows) == 1 and rows[0]["title"] == "Synthetic CLI guide — guía"
