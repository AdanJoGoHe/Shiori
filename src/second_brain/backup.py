"""Local, bounded recovery bundles; restore only into a new deployment."""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from second_brain.annotations import Annotations, decode
from second_brain.core import Brain, SLUG, TYPES, atomic_write, scoped_path, validate_note

MAX_BYTES = 64_000_000
MAX_FILE_BYTES = 8_000_000
MAX_FILES = 5000
NOTE = r"(?:" + "|".join(sorted(set(TYPES.values()))) + r")/[a-z0-9][a-z0-9-]{0,99}\.md"
VAULT_FILE = re.compile(
    rf"(?:{NOTE}|journal/\d{{4}}/\d{{4}}-\d{{2}}-\d{{2}}\.md|"
    r"archive/[a-z0-9][a-z0-9-]{0,99}/[a-f0-9]{16}\.md)\Z"
)


def local_path(value):
    path = Path(value).absolute()
    return scoped_path(Path(path.anchor), path.relative_to(path.anchor))


def allowed_file(name):
    return name in {"state/ledger.json", "state/annotations.json"} or (
        name.startswith("vault/") and VAULT_FILE.fullmatch(name[6:])
    )


def read_bounded(path):
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Backup file exceeds size limit")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Backup file exceeds size limit")
    raw.decode("utf-8")
    return raw


def validate_files(files):
    if not files or len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("Backup exceeds file or byte limits")
    if any(not allowed_file(name) for name in files) or "state/ledger.json" not in files:
        raise ValueError("Unsupported backup paths or missing ledger")
    ledger = json.loads(files["state/ledger.json"])
    if not isinstance(ledger, dict) or set(ledger) != {"notes", "events"}:
        raise ValueError("Invalid backup ledger")
    if not isinstance(ledger["notes"], dict) or not isinstance(ledger["events"], dict):
        raise ValueError("Invalid backup ledger maps")
    for note_id, relative in ledger["notes"].items():
        if (
            not SLUG.fullmatch(note_id)
            or not isinstance(relative, str)
            or not re.fullmatch(NOTE, relative)
            or Path(relative).stem != note_id
            or f"vault/{relative}" not in files
        ):
            raise ValueError("Missing or invalid canonical note")
    for event_id, item in ledger["events"].items():
        if (
            not SLUG.fullmatch(event_id)
            or not isinstance(item, dict)
            or set(item) != {"status", "fingerprint", "path", "at"}
            or item["status"] not in ("pending", "committed")
            or not isinstance(item["fingerprint"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["fingerprint"])
            or not isinstance(item["path"], str)
            or not VAULT_FILE.fullmatch(item["path"])
            or not isinstance(item["at"], str)
        ):
            raise ValueError("Invalid backup event")
        moment = datetime.fromisoformat(item["at"])
        if moment.tzinfo is None:
            raise ValueError("Backup event requires timezone")
        if item["status"] == "committed":
            journal = files.get(f"vault/journal/{moment:%Y}/{moment:%Y-%m-%d}.md", b"")
            if (
                f"vault/{item['path']}" not in files
                or f"<!-- event:{event_id} -->".encode() not in journal
            ):
                raise ValueError("Incomplete committed backup event")
    if "state/annotations.json" in files:
        decode(files["state/annotations.json"].decode("utf-8"))
    return ledger


def write_files(destination, files):
    # Exclusive directory creation is the no-overwrite boundary. Leave partial failures visible.
    destination.mkdir(mode=0o700)
    for name, raw in files.items():
        path = scoped_path(destination, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def backup(brain, output):
    output = local_path(output)
    if any(
        output.is_relative_to(root) or root.is_relative_to(output)
        for root in (brain.vault, brain.state)
    ):
        raise ValueError("Backup destination must be separate from vault and state")
    if output.exists():
        raise ValueError("Backup destination already exists")
    with brain.lock, Annotations(brain).lock:
        files = {}
        for folder in sorted(set(TYPES.values()) | {"journal", "archive"}):
            root = brain.path(folder)
            for path in root.rglob("*"):
                relative = path.relative_to(brain.vault).as_posix()
                checked = brain.path(relative)
                if checked.is_dir():
                    continue
                name = f"vault/{relative}"
                if not allowed_file(name):
                    raise ValueError("Unsupported file inside canonical vault folders")
                files[name] = read_bounded(checked)
                if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_BYTES:
                    raise ValueError("Backup exceeds file or byte limits")
        ledger_path = scoped_path(brain.state, "ledger.json")
        if files and not ledger_path.exists():
            raise ValueError("Missing ledger for a nonempty canonical vault")
        files["state/ledger.json"] = (
            read_bounded(ledger_path) if ledger_path.exists() else b'{"events": {}, "notes": {}}'
        )
        annotation_path = scoped_path(brain.state, "annotations.json")
        if annotation_path.exists():
            files["state/annotations.json"] = read_bounded(annotation_path)
        ledger = validate_files(files)
        for note_id in ledger["notes"]:
            brain.read(note_id)
        manifest = {
            "schema_version": 1,
            "scope": "personal",
            "timezone": brain.config["timezone"],
            "created_at": brain.now().isoformat(),
            "source_paused": (brain.state / "paused").exists(),
            "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        }
    write_files(output, files)
    atomic_write(output / "manifest.json", json.dumps(manifest, indent=2))
    return {"status": "backed-up", "files": len(files), "bytes": sum(map(len, files.values()))}


def read_bundle(source):
    source = local_path(source)
    manifest = json.loads(read_bounded(scoped_path(source, "manifest.json")))
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {"schema_version", "scope", "timezone", "created_at", "source_paused", "files"}
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["scope"] != "personal"
        or type(manifest["source_paused"]) is not bool
        or not isinstance(manifest["timezone"], str)
        or not isinstance(manifest["created_at"], str)
        or not isinstance(manifest["files"], dict)
        or not 1 <= len(manifest["files"]) <= MAX_FILES
    ):
        raise ValueError("Unsupported backup manifest")
    ZoneInfo(manifest["timezone"])
    if datetime.fromisoformat(manifest["created_at"]).tzinfo is None:
        raise ValueError("Backup timestamp requires timezone")
    files = {}
    for name, expected in manifest["files"].items():
        if not allowed_file(name):
            raise ValueError("Unsupported backup path")
        raw = read_bounded(scoped_path(source, name))
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Backup integrity mismatch")
        files[name] = raw
        if sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError("Backup exceeds byte limit")
    ledger = validate_files(files)
    for note_id, relative in ledger["notes"].items():
        try:
            content = files[f"vault/{relative}"].decode("utf-8")
            validate_note(content.replace("\r\n", "\n").replace("\r", "\n"), note_id)
        except (ValueError, TypeError, KeyError):
            raise ValueError("Invalid canonical note in backup") from None
    return manifest, files, ledger


def restore(source, destination):
    source, destination = local_path(source), local_path(destination)
    if (
        destination.exists()
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("Restore requires a new destination separate from the backup")
    manifest, files, ledger = read_bundle(source)
    write_files(destination, files)
    config = {
        "schema_version": 1,
        "scope": "personal",
        "timezone": manifest["timezone"],
        "vault_path": str(destination / "vault"),
        "state_path": str(destination / "state"),
        "basic_memory_config_dir": str(destination / "state/basic-memory"),
    }
    restored = Brain(config)
    for note_id in ledger["notes"]:
        restored.read(note_id)
    restored.pause(True)
    # Configuration is the completion marker; incomplete restores cannot be selected as deployments.
    atomic_write(destination / "config.json", json.dumps(config, indent=2))
    return {
        "status": "restored",
        "files": len(files),
        "notes": len(ledger["notes"]),
        "paused": True,
    }
