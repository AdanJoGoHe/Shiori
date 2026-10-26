import hashlib
import json
import subprocess
import sys

import pytest

from second_brain import backup as recovery
from second_brain.annotations import Annotations
from second_brain.core import Brain, load_config
from test_core import brain as brain, event


def test_roundtrip_preserves_bytes_history_journal_and_dedup(brain, tmp_path):
    brain.capture(event(tags=["python"], project="one"))
    brain.capture(event(event_id="updated", body="Updated observation"))
    annotations = Annotations(brain)
    document = {
        "item": {"id": "note:personal:commands/git-version.md"},
        "revision": "a" * 64,
        "text": "Synthetic observation",
    }
    annotations.save(
        document,
        {
            "document_id": document["item"]["id"],
            "revision": document["revision"],
            "start": 0,
            "end": 9,
            "quote": "Synthetic",
            "color": "yellow",
            "tags": ["informacion-importante"],
            "title": "Lección recuperable 😀",
            "description": "Cuándo resulta útil esta observación.",
        },
    )
    annotations.restore(json.dumps(annotations.export()))
    brain.pause(True)
    config = dict(brain.config)
    config["documentation_roots"] = {"private-path": "not-exported"}
    brain.config = config
    bundle = tmp_path / "bundle"
    result = recovery.backup(brain, bundle)
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert result["status"] == "backed-up"
    assert "not-exported" not in json.dumps(manifest)
    destination = tmp_path / "restored"
    assert recovery.restore(bundle, destination)["paused"] is True
    restored = Brain(load_config(destination / "config.json"))
    assert restored.read("git-version") == brain.read("git-version")
    for original in brain.vault.rglob("*.md"):
        assert (
            restored.vault / original.relative_to(brain.vault)
        ).read_bytes() == original.read_bytes()
    assert (restored.state / "ledger.json").read_bytes() == brain.ledger_path.read_bytes()
    assert Annotations(restored).export() == Annotations(brain).export()
    assert restored.capture(event())["reason"] == "paused"
    restored.pause(False)
    assert restored.capture(event(tags=["python"], project="one"))["status"] == "duplicate"
    assert (restored.state / "annotations.previous.json").exists() is False
    assert "documentation_roots" not in restored.config


def test_pending_capture_survives_restore_and_can_retry(brain, tmp_path, monkeypatch):
    import second_brain.core as core

    original = core.atomic_write

    def fail(path, content):
        if "journal" in path.parts:
            raise OSError("Synthetic interruption")
        original(path, content)

    monkeypatch.setattr(core, "atomic_write", fail)
    with pytest.raises(OSError):
        brain.capture(event())
    monkeypatch.setattr(core, "atomic_write", original)
    recovery.backup(brain, tmp_path / "bundle")
    recovery.restore(tmp_path / "bundle", tmp_path / "restored")
    restored = Brain(load_config(tmp_path / "restored/config.json"))
    assert restored.status()["pending"] == 1
    restored.pause(False)
    assert restored.capture(event())["status"] == "saved"
    assert restored.status()["pending"] == 0
    assert brain.status()["pending"] == 1


@pytest.mark.parametrize(
    "mutation", ["hash", "traversal", "case", "scope", "missing", "schema", "ledger"]
)
def test_invalid_bundle_rejected_without_touching_active_deployment(brain, tmp_path, mutation):
    brain.capture(event())
    original = brain.read("git-version")
    ledger = brain.ledger_path.read_bytes()
    bundle = tmp_path / "bundle"
    recovery.backup(brain, bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "hash":
        (bundle / "vault/commands/git-version.md").write_text("Changed", encoding="utf-8")
    elif mutation == "traversal":
        manifest["files"]["vault/../outside.md"] = "0" * 64
    elif mutation == "case":
        manifest["files"]["STATE/ledger.json"] = "0" * 64
    elif mutation == "scope":
        manifest["scope"] = "work"
    elif mutation == "schema":
        manifest["schema_version"] = 2
    elif mutation == "missing":
        (bundle / "state/ledger.json").unlink()
    elif mutation == "ledger":
        raw = json.dumps({"notes": {"escape": "../outside.md"}, "events": {}}).encode()
        (bundle / "state/ledger.json").write_bytes(raw)
        manifest["files"]["state/ledger.json"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        recovery.restore(bundle, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    assert brain.read("git-version") == original
    assert brain.ledger_path.read_bytes() == ledger


def test_existing_destinations_and_overlapping_paths_never_overwritten(brain, tmp_path):
    bundle = tmp_path / "bundle"
    recovery.backup(brain, bundle)
    before = (bundle / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="exists"):
        recovery.backup(brain, bundle)
    for path in (brain.vault, brain.vault / "backup", brain.state / "backup"):
        with pytest.raises(ValueError):
            recovery.backup(brain, path)
    for path in (bundle, bundle / "restored", brain.vault):
        with pytest.raises(ValueError):
            recovery.restore(bundle, path)
    assert (bundle / "manifest.json").read_bytes() == before


def test_junctions_and_resource_limits_fail_closed(brain, tmp_path, monkeypatch):
    brain.capture(event())
    monkeypatch.setattr(recovery, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="limit"):
        recovery.backup(brain, tmp_path / "too-large")
    assert not (tmp_path / "too-large").exists()
    monkeypatch.setattr(recovery, "MAX_BYTES", 64_000_000)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = brain.vault / "knowledge"
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(linked), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Linked"):
        recovery.backup(brain, tmp_path / "linked-backup")
    assert list(outside.iterdir()) == []


def test_cli_recovery_without_original_config(brain, tmp_path):
    brain.capture(event())
    config = tmp_path / "source.json"
    config.write_text(json.dumps(dict(brain.config, schema_version=1)), encoding="utf-8")
    bundle = tmp_path / "bundle"

    def run(*args):
        result = subprocess.run(
            [sys.executable, "-m", "second_brain.cli", *map(str, args)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    assert run("--config", config, "backup", "--output", bundle)["status"] == "backed-up"
    config.unlink()
    assert (
        run(
            "--config", config, "restore", "--input", bundle, "--destination", tmp_path / "restored"
        )["status"]
        == "restored"
    )
    assert (
        run("--config", tmp_path / "restored/config.json", "doctor")["note_validation"] == "passed"
    )


def test_linked_bundle_is_rejected_before_destination_creation(brain, tmp_path):
    bundle = tmp_path / "bundle"
    recovery.backup(brain, bundle)
    linked = tmp_path / "linked-bundle"
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(linked), str(bundle)], check=True, capture_output=True
        )
    else:
        linked.symlink_to(bundle, target_is_directory=True)
    with pytest.raises(ValueError, match="Linked"):
        recovery.restore(linked, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_incomplete_outputs_cannot_be_loaded_as_complete(brain, tmp_path, monkeypatch):
    brain.capture(event())
    original = recovery.atomic_write

    def fail(path, content):
        raise OSError("Synthetic completion failure")

    monkeypatch.setattr(recovery, "atomic_write", fail)
    with pytest.raises(OSError):
        recovery.backup(brain, tmp_path / "incomplete")
    assert not (tmp_path / "incomplete/manifest.json").exists()
    with pytest.raises(OSError):
        recovery.restore(tmp_path / "incomplete", tmp_path / "rejected")
    monkeypatch.setattr(recovery, "atomic_write", original)
    recovery.backup(brain, tmp_path / "good")
    monkeypatch.setattr(recovery, "atomic_write", fail)
    with pytest.raises(OSError):
        recovery.restore(tmp_path / "good", tmp_path / "partial-restore")
    assert not (tmp_path / "partial-restore/config.json").exists()
