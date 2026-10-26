import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from second_brain import transfer
from second_brain.annotations import Annotations
from second_brain.backup import backup, restore
from second_brain.core import Brain, load_config
from test_core import event


def deployment(root):
    return Brain(
        {
            "scope": "personal",
            "vault_path": str(root / "vault"),
            "state_path": str(root / "state"),
            "timezone": "Europe/Madrid",
        }
    )


def snapshot(brain):
    return {
        path: path.read_bytes()
        for root in [brain.vault, brain.state]
        for path in root.rglob("*")
        if path.is_file() and path.name != "capture.lock"
    }


@pytest.fixture
def bundle(tmp_path):
    source = deployment(tmp_path / "source")
    source.capture(
        event(tags=["python", "comando"], project="second-brain", related=["another-note"])
    )
    path = tmp_path / "bundle"
    backup(source, path)
    return source, path


def test_additive_preview_apply_preserves_existing_bytes_metadata_and_repeat(tmp_path, monkeypatch):
    source, target = deployment(tmp_path / "source"), deployment(tmp_path / "target")
    source.now = lambda: datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    source.capture(event())
    with monkeypatch.context() as clock:
        clock.setattr(target, "now", source.now)
        target.capture(event())
    source.capture(event(id="conflicting-note", event_id="source-conflict", body="Incoming"))
    target.capture(event(id="conflicting-note", event_id="local-conflict", body="Local stays"))
    source.capture(
        event(
            id="new-note",
            event_id="new-event",
            title="Comando útil 😀",
            tags=["comando"],
            project="second-brain",
            related=["git-version"],
            source_refs=["Manual local"],
            sensitivity="private",
        )
    )
    new_path = source.path("commands/new-note.md")
    new_path.write_bytes(new_path.read_bytes().replace(b"\n", b"\r\n"))
    Annotations(source).restore(json.dumps(Annotations(source).export()))
    Annotations(target).restore(json.dumps(Annotations(target).export()))
    # Existing journal bytes are a prefix after adding the local import entry.
    journal = target.path(f"journal/{target.now():%Y}/{target.now():%Y-%m-%d}.md")
    journal.write_bytes(journal.read_bytes().replace(b"\n", b"\r\n"))
    path = tmp_path / "bundle"
    backup(source, path)
    original, ledger = snapshot(target), target.ledger()
    bundle_before = {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    preview = transfer.import_memory(target, path)
    assert preview["status"] == "preview"
    assert (preview["additions"], preview["duplicates"], preview["conflicts"]) == (1, 1, 1)
    assert snapshot(target) == original
    applied = transfer.import_memory(target, path, apply=True)
    assert applied["status"] == "imported" and applied["items"] == preview["items"]
    assert target.path("commands/new-note.md").read_bytes() == new_path.read_bytes()
    assert "2024-01-02" in target.read("new-note")
    assert (
        target.search("", filters={"tags": ["comando"], "project": "second-brain"})[0]["id"]
        == "new-note"
    )
    assert target.ledger()["notes"].items() >= ledger["notes"].items()
    for event_id, row in ledger["events"].items():
        assert target.ledger()["events"][event_id] == row
    for name, raw in original.items():
        if name == journal:
            assert name.read_bytes().startswith(raw)
        elif name != target.ledger_path:
            assert name.read_bytes() == raw
    assert bundle_before == {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    after = snapshot(target)
    repeated = transfer.import_memory(target, path, apply=True)
    assert (repeated["additions"], repeated["duplicates"], repeated["conflicts"]) == (0, 2, 1)
    assert snapshot(target) == after
    assert not (target.vault / "archive").exists()
    backup(target, tmp_path / "after-import")
    restore(tmp_path / "after-import", tmp_path / "recovered")
    recovered = Brain(load_config(tmp_path / "recovered/config.json"))
    assert recovered.read("new-note") == target.read("new-note")
    assert transfer.import_memory(recovered, path)["duplicates"] == 2


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5])
def test_interrupted_import_retries_exact_bundle_once(bundle, tmp_path, monkeypatch, step):
    source, _ = bundle
    source.capture(event(id="second-note", event_id="second-note"))
    path = tmp_path / "two-note-bundle"
    backup(source, path)
    target = deployment(tmp_path / "target")
    original, calls = transfer.atomic_write, []

    def interrupted(path, content):
        original(path, content)
        calls.append(path)
        if len(calls) == step:
            raise OSError("Synthetic interrupted import")

    monkeypatch.setattr(transfer, "atomic_write", interrupted)
    with pytest.raises(OSError):
        transfer.import_memory(target, path, apply=True)
    monkeypatch.setattr(transfer, "atomic_write", original)
    assert transfer.import_memory(target, path, apply=True)["status"] == "imported"
    assert target.status()["notes"] == 2 and target.status()["pending"] == 0
    events = [name for name in target.ledger()["events"] if name.startswith("import-")]
    assert len(events) == 2
    text = next(target.vault.glob("journal/*/*.md")).read_text(encoding="utf-8")
    assert all(text.count(f"<!-- event:{event_id} -->") == 1 for event_id in events)
    before = snapshot(target)
    assert transfer.import_memory(target, path, apply=True)["additions"] == 0
    assert snapshot(target) == before


@pytest.mark.parametrize(
    "mutation", ["hash", "note-schema", "note-id", "scope", "secret", "traversal"]
)
def test_invalid_import_is_fully_validated_before_writes(bundle, tmp_path, mutation):
    _, path = bundle
    target = deployment(tmp_path / "target")
    target.capture(event(id="existing", event_id="existing"))
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    note = path / "vault/commands/git-version.md"
    content = note.read_text(encoding="utf-8")
    if mutation == "hash":
        note.write_text("tampered", encoding="utf-8")
    elif mutation == "scope":
        manifest["scope"] = "work"
    elif mutation == "traversal":
        manifest["files"]["vault/../escape.md"] = "0" * 64
    else:
        if mutation == "note-schema":
            content = content.replace("schema_version: 1", "schema_version: 2")
        elif mutation == "note-id":
            content = content.replace("id: git-version", "id: wrong-note")
        else:
            content += "\npassword=syntheticpassword\n"
        note.write_text(content, encoding="utf-8")
        manifest["files"]["vault/commands/git-version.md"] = hashlib.sha256(
            note.read_bytes()
        ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = snapshot(target)
    with pytest.raises((ValueError, OSError)):
        transfer.import_memory(target, path, apply=True)
    assert snapshot(target) == before


def test_two_importers_serialize_and_do_not_duplicate(bundle, tmp_path):
    _, path = bundle
    target = deployment(tmp_path / "target")
    other = Brain(target.config)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda brain: transfer.import_memory(brain, path, True), [target, other])
        )
    assert sorted(result["additions"] for result in results) == [0, 1]
    assert target.status()["pending"] == 0
    assert len(target.ledger()["events"]) == 1


def test_pause_unmanaged_files_and_foreign_pending_are_preserved(bundle, tmp_path, monkeypatch):
    _, path = bundle
    target = deployment(tmp_path / "target")
    target.pause(True)
    assert transfer.import_memory(target, path)["additions"] == 1
    before = snapshot(target)
    assert transfer.import_memory(target, path, True)["reason"] == "paused"
    assert snapshot(target) == before
    target.pause(False)
    unmanaged = target.path("commands/git-version.md")
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_bytes(b"Local unmanaged note")
    assert transfer.import_memory(target, path, True)["conflicts"] == 1
    assert unmanaged.read_bytes() == b"Local unmanaged note"
    target.capture(event(id="other", event_id="other"))
    ledger = target.ledger()
    ledger["events"]["other"]["status"] = "pending"
    target.ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    before = snapshot(target)
    result = transfer.import_memory(target, path, True)
    assert result == {"status": "blocked", "reason": "pending-captures", "event_ids": ["other"]}
    assert snapshot(target) == before


def test_changed_interrupted_import_never_replaces_manual_edit(bundle, tmp_path, monkeypatch):
    _, path = bundle
    target = deployment(tmp_path / "target")
    original = transfer.atomic_write

    def interrupted(path, content):
        original(path, content)
        if path.suffix == ".md":
            raise OSError("Synthetic interruption after note")

    monkeypatch.setattr(transfer, "atomic_write", interrupted)
    with pytest.raises(OSError):
        transfer.import_memory(target, path, True)
    monkeypatch.setattr(transfer, "atomic_write", original)
    target.path("commands/git-version.md").write_bytes(b"Manual edit stays")
    before = snapshot(target)
    assert transfer.import_memory(target, path, True)["reason"] == "pending-import-conflict"
    assert snapshot(target) == before


def test_source_pending_and_overlapping_input_are_rejected(bundle, tmp_path):
    _, path = bundle
    target = deployment(tmp_path / "target")
    with pytest.raises(ValueError, match="separate"):
        transfer.import_memory(target, target.vault, True)
    ledger_path = path / "state/ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["events"]["test-event"]["status"] = "pending"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["state/ledger.json"] = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = snapshot(target)
    with pytest.raises(ValueError, match="Source has pending"):
        transfer.import_memory(target, path, True)
    assert snapshot(target) == before


def test_cli_export_preview_and_apply_preserve_unrelated_deployment(bundle, tmp_path):
    source, _ = bundle
    target = deployment(tmp_path / "target")

    def cli(brain, *args):
        config = brain.state / "config-for-test.json"
        config.write_text(json.dumps({**brain.config, "schema_version": 1}), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "second_brain.cli", "--config", str(config), *map(str, args)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    output = tmp_path / "export"
    assert cli(source, "export-memory", "--output", output)["status"] == "backed-up"
    assert cli(target, "import-memory", "--input", output)["status"] == "preview"
    assert target.status()["notes"] == 0
    assert cli(target, "import-memory", "--input", output, "--apply")["additions"] == 1
    assert target.read("git-version") == source.read("git-version")
