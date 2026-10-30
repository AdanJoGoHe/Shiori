"""Read-only path diagnostics and explicit same-store configuration repair."""

import hashlib
import json
import os
import uuid
from pathlib import Path

from filelock import FileLock, Timeout

from second_brain.core import atomic_write, canonical_root, load_config, scoped_path

FIELDS = ("vault_path", "state_path", "basic_memory_config_dir")
MAX_CONFIG = 128_000
MAX_LEDGER = 8_000_000
MAX_ANCHORS = 5000


class Refused(ValueError):
    pass


def read_bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise Refused("inspection-limit")
    return raw


def lexical_child(root, relative):
    """Stat-only namespace probe; never open a file outside scoped_path."""
    root, relative = Path(root), Path(relative)
    if not root.is_absolute() or relative.is_absolute() or ".." in relative.parts:
        raise Refused("invalid-path")
    child = root / relative
    if any(p.is_symlink() or p.is_junction() for p in [child, *child.parents]):
        raise Refused("linked-path")
    return child


def same_store(old, new, anchors):
    old, new = Path(old), canonical_root(new)
    canonical_root(old)  # Reject root/ancestor links before inspecting either namespace.
    if canonical_root(old) == new:
        return True
    try:
        if old.samefile(new):
            return True
    except FileNotFoundError:
        pass
    if not anchors or len(anchors) > MAX_ANCHORS:
        return False
    for relative in anchors:
        before = lexical_child(old, relative)
        after = scoped_path(new, relative)
        if before.resolve() != after or not before.samefile(after):
            return False
    return True


def diagnose(config_path):
    try:
        raw = read_bounded(Path(config_path), MAX_CONFIG)
        configuration_id = hashlib.sha256(str(Path(config_path).resolve()).encode()).hexdigest()[
            :16
        ]
        config = json.loads(raw.decode("utf-8-sig"))
        if (
            config.get("scope") not in {"personal", "work"}
            or config.get("schema_version") != 1
            or not {"vault_path", "state_path"}.issubset(config)
        ):
            raise Refused("invalid-configuration")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "unavailable", "reason": "invalid-or-unavailable-configuration"}
    roots = {}
    for field in FIELDS:
        if field not in config:
            continue
        try:
            original = Path(config[field])
            root = canonical_root(original)
            probes = ["ledger.json", "config.json", "knowledge", "commands", "journal", "README.md"]
            coherent = all(
                not (child := lexical_child(original, name)).exists()
                or child.resolve().is_relative_to(root)
                for name in probes
            )
            code = (
                "missing-root"
                if not root.is_dir()
                else "inconsistent-resolution"
                if not coherent
                else "canonicalization-needed"
                if str(original) != str(root)
                else "ok"
            )
            roots[field] = {
                "code": code,
                "root_id": hashlib.sha256(str(root).encode()).hexdigest()[:16],
            }
        except (OSError, ValueError, TypeError):
            roots[field] = {"code": "invalid-or-unavailable-root"}
    return {
        "status": "ok" if roots and all(r["code"] == "ok" for r in roots.values()) else "attention",
        "configuration_revision": hashlib.sha256(raw).hexdigest(),
        "configuration_id": configuration_id,
        "roots": roots,
    }


def plan(config_path, overrides):
    raw = read_bounded(config_path, MAX_CONFIG)
    original = json.loads(raw.decode("utf-8-sig"))
    proposed = load_config(config_path)
    if set(overrides) - set(FIELDS):
        raise Refused("invalid-override")
    for field, value in overrides.items():
        if value is not None:
            if field not in original:
                raise Refused("not-configured")
            proposed[field] = str(canonical_root(value))
    vault, state = (canonical_root(proposed[key]) for key in FIELDS[:2])
    if not vault.is_dir() or not state.is_dir():
        raise Refused("missing-root")
    if vault.is_relative_to(state) or state.is_relative_to(vault):
        raise Refused("overlapping-roots")
    state_anchors = [
        name
        for name in [
            "ledger.json",
            "annotations.json",
            "annotations.previous.json",
            "task-pages.json",
            "install-manifest.json",
            "paused",
        ]
        if lexical_child(Path(original["state_path"]), name).exists() or (state / name).exists()
    ]
    if not same_store(original["state_path"], state, state_anchors):
        raise Refused("different-state-store")
    ledger_path = scoped_path(state, "ledger.json")
    ledger = (
        json.loads(read_bounded(ledger_path, MAX_LEDGER))
        if ledger_path.exists()
        else {"notes": {}, "events": {}}
    )
    anchors = set(ledger["notes"].values()) | {e["path"] for e in ledger["events"].values()}
    if (
        lexical_child(Path(original["vault_path"]), "README.md").exists()
        or (vault / "README.md").exists()
    ):
        anchors.add("README.md")
    if len(anchors) > MAX_ANCHORS or len(ledger["notes"]) > MAX_ANCHORS:
        raise Refused("inspection-limit")
    anchors = {
        relative
        for relative in anchors
        if lexical_child(Path(original["vault_path"]), relative).exists()
        or scoped_path(vault, relative).exists()
    }
    if not same_store(original["vault_path"], vault, anchors):
        raise Refused("different-vault-store")
    if proposed.get("basic_memory_config_dir") and not same_store(
        original.get("basic_memory_config_dir", proposed["basic_memory_config_dir"]),
        proposed["basic_memory_config_dir"],
        ["config.json"],
    ):
        raise Refused("different-provider-store")
    # Identity checks use filesystem metadata, not note bodies or a creating Brain constructor.
    changes = {
        field: {"before": original.get(field), "after": proposed[field]}
        for field in FIELDS
        if field in proposed and original.get(field) != proposed[field]
    }
    return raw, proposed, changes


def repair(config_path, overrides=None, apply=False, expected_revision=None):
    """Preview never writes; apply snapshots exact config bytes before atomic replacement."""
    try:
        lexical_child(Path(config_path).absolute().parent, Path(config_path).name)
        config_path = Path(config_path).resolve(strict=True)
        raw, proposed, changes = plan(config_path, overrides or {})
        revision = hashlib.sha256(raw).hexdigest()
        if expected_revision and expected_revision != revision:
            raise Refused("configuration-changed")
        result = {
            "status": "ready" if changes else "no-change",
            "configuration_revision": revision,
            "config_path": str(config_path),
            "proposed_roots": {field: proposed[field] for field in FIELDS if proposed.get(field)},
            "changes": changes,
            "restart_required": False,
        }
        if not apply or not changes:
            return result
        with FileLock(str(config_path) + ".paths.lock", timeout=5):
            current, current_proposed, _ = plan(config_path, overrides or {})
            if current != raw or current_proposed != proposed:
                raise Refused("configuration-changed")
            backup = config_path.with_name(
                config_path.name + ".paths-before-" + uuid.uuid4().hex + ".json"
            )
            with backup.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            atomic_write(config_path, json.dumps(proposed, ensure_ascii=False, indent=2) + "\n")
        return {
            **result,
            "status": "repaired",
            "backup": str(backup),
            "restart_required": True,
            "provider_review_required": True,
            "host_integration_review_required": True,
        }
    except Refused as error:
        return {"status": "blocked", "reason": str(error)}
    except Timeout:
        return {"status": "blocked", "reason": "busy"}
    except OSError:
        return {"status": "blocked", "reason": "unavailable"}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"status": "blocked", "reason": "invalid-configuration"}
