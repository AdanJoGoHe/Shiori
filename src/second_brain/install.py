"""Merge owned blocks with byte-for-byte backups; preserve unrelated settings."""

import hashlib
import json
import sys
import tomllib
import uuid
from importlib.resources import files
from pathlib import Path

from filelock import FileLock

from second_brain.core import atomic_write, load_config

BEGIN = "# BEGIN SECOND BRAIN PERSONAL"
END = "# END SECOND BRAIN PERSONAL"


def checksum(content):
    return hashlib.sha256(content).hexdigest()


def integration_blocks(config_path):
    # Resolving a venv symlink on Linux selects the base Python without its packages.
    executable = str(Path(sys.executable).absolute()).replace("\\", "/")
    cfg = str(config_path.resolve()).replace("\\", "/")
    server_block = (
        f"{BEGIN}\n[mcp_servers.second_brain_personal]\n"
        f'command = "{executable}"\n'
        f'args = ["-m", "second_brain.cli", "--config", "{cfg}", "serve"]\n'
        f"startup_timeout_sec = 30\ntool_timeout_sec = 45\n{END}\n"
    )
    instructions = (
        f"{BEGIN}\nBefore substantial personal technical work, use the Second Brain skill "
        "to retrieve relevant memories. At meaningful completion, capture reusable verified "
        "lessons and journal progress through the skill. Use only the personal deployment; "
        f"skip corporate material and trivial interactions.\n{END}\n"
    )
    return server_block, instructions


def packaged_skill():
    source = files("second_brain").joinpath("resources/second-brain/SKILL.md")
    if not source.is_file():  # Editable source checkouts use the same canonical skill.
        source = Path(__file__).resolve().parents[2] / "skills/second-brain/SKILL.md"
    return source.read_text(encoding="utf-8")


def deployment_config(config_path):
    from second_brain.paths import diagnose

    config = load_config(config_path)
    if config["scope"] != "personal":
        raise ValueError("This integration manages personal scope only")
    report = diagnose(config_path)
    if any(
        report.get("roots", {}).get(field, {}).get("code")
        in {"inconsistent-resolution", "invalid-or-unavailable-root"}
        for field in ["vault_path", "state_path"]
    ):
        raise ValueError("Deployment paths require explicit repair")
    return config


def install(config_path):
    config = deployment_config(config_path)
    state = Path(config["state_path"])
    manifest_path = state / "install-manifest.json"
    if manifest_path.exists():
        return {"status": "already installed", "manifest": str(manifest_path)}
    codex = Path.home() / ".codex"
    codex.mkdir(exist_ok=True)
    config_file = codex / "config.toml"
    current = config_file.read_bytes() if config_file.exists() else b""
    parsed = tomllib.loads(current.decode("utf-8-sig"))
    if "second_brain_personal" in parsed.get("mcp_servers", {}):
        raise ValueError("Existing Shiori server requires manual reconciliation")
    server_block, instructions = integration_blocks(config_path)
    skill_target = codex / "skills/second-brain/SKILL.md"
    if skill_target.exists():
        raise ValueError("Existing second-brain skill will not be overwritten")
    agents_file = codex / "AGENTS.md"
    agents_current = agents_file.read_bytes() if agents_file.exists() else b""
    if BEGIN.encode() in agents_current:
        raise ValueError("Unmanaged Shiori instruction block exists")
    entries = []
    for target, original, block in [
        (config_file, current, server_block),
        (agents_file, agents_current, instructions),
    ]:
        backup = state / "backups" / uuid.uuid4().hex / target.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original)
        text = original.decode("utf-8-sig")
        updated = text + ("\n" if text and not text.endswith("\n") else "") + "\n" + block
        if target == config_file:
            tomllib.loads(updated)
        entries.append(
            {
                "path": str(target),
                "backup": str(backup),
                "block": block,
                "before": checksum(original),
                "after": checksum(updated.encode()),
            }
        )
    skill = packaged_skill()
    manifest = {
        "entries": entries,
        "skill": str(skill_target),
        "skill_hash": checksum(skill.encode()),
    }
    # Persist recovery information before altering user configuration.
    atomic_write(manifest_path, json.dumps(manifest, indent=2))
    for entry in entries:
        target = Path(entry["path"])
        original = Path(entry["backup"]).read_bytes().decode("utf-8-sig")
        updated = (
            original
            + ("\n" if original and not original.endswith("\n") else "")
            + "\n"
            + entry["block"]
        )
        atomic_write(target, updated)
    atomic_write(skill_target, skill)
    return {"status": "installed", "manifest": str(manifest_path), "restart_required": True}


def upgrade(config_path, apply=False):
    """Preview by default; only replace files still owned by the installation manifest."""
    state = Path(deployment_config(config_path)["state_path"])
    if not apply:
        return _upgrade(config_path, state, False)
    with FileLock(state / "install-upgrade.lock", timeout=5):
        return _upgrade(config_path, state, True)


def _upgrade(config_path, state, apply):
    codex = Path.home() / ".codex"
    manifest_path = state / "install-manifest.json"

    def read_regular(path):
        # Windows short-name aliases resolve differently without being links.
        if not path.is_file() or any(
            part.is_symlink() or part.is_junction() for part in (path, *path.parents)
        ):
            raise ValueError(f"Expected an existing regular owned file: {path}")
        return path.read_bytes()

    manifest_raw = read_regular(manifest_path)
    manifest = json.loads(manifest_raw)
    targets = [codex / "config.toml", codex / "AGENTS.md"]
    skill = codex / "skills/second-brain/SKILL.md"
    if [Path(e["path"]) for e in manifest["entries"]] != targets or Path(
        manifest["skill"]
    ) != skill:
        raise ValueError("Installation manifest targets require manual reconciliation")
    originals = {p: read_regular(p) for p in [*targets, skill]}
    replacements = {}
    baselines = {}
    blocks = integration_blocks(config_path)
    for entry, target, new_block in zip(manifest["entries"], targets, blocks, strict=True):
        raw = originals[target]
        old = entry["block"].encode()
        if old not in raw:
            old = entry["block"].replace("\n", "\r\n").encode()
        if raw.count(old) != 1 or raw.count(BEGIN.encode()) != 1 or raw.count(END.encode()) != 1:
            raise ValueError(f"Owned block modified or duplicated; reconcile manually: {target}")
        replacement = new_block.encode()
        if b"\r\n" in old:
            replacement = new_block.replace("\n", "\r\n").encode()
        updated = raw.replace(old, replacement, 1)
        if target.name == "config.toml":
            tomllib.loads(updated.decode("utf-8-sig"))
        # Keep later user additions when uninstall restores a whole-file snapshot.
        if checksum(raw) == entry["after"]:
            backup = Path(entry["backup"])
            if not backup.resolve().is_relative_to((state / "backups").resolve()):
                raise ValueError("Installation backup is outside the state backups directory")
            baseline = read_regular(backup)
            if checksum(baseline) != entry["before"]:
                raise ValueError("Installation backup checksum mismatch")
        else:
            baseline = raw.replace(old, b"", 1)
        baselines[target] = baseline
        replacements[target] = updated
    if checksum(originals[skill]) != manifest["skill_hash"]:
        raise ValueError("Installed skill modified; reconcile manually before upgrading")
    replacements[skill] = packaged_skill().encode()
    changes = [p for p in replacements if replacements[p] != originals[p]]
    result = {
        "status": "upgrade available" if changes else "up to date",
        "applied": False,
        "changes": [str(p) for p in changes],
        "restart_required": False,
    }
    if not apply or not changes:
        return result

    recovery = state / "backups" / f"upgrade-{uuid.uuid4().hex}"
    recovery.mkdir(parents=True, exist_ok=False)
    # Full snapshots precede mutations; retain them even after a successful rollback.
    snapshots = {**originals, manifest_path: manifest_raw}
    for path, raw in snapshots.items():
        (recovery / path.name).write_bytes(raw)
    for entry, target, block in zip(manifest["entries"], targets, blocks, strict=True):
        baseline = recovery / f"uninstall-{target.name}"
        baseline.write_bytes(baselines[target])
        entry.update(
            backup=str(baseline),
            before=checksum(baselines[target]),
            after=checksum(replacements[target]),
            block=block,
        )
    manifest["skill_hash"] = checksum(replacements[skill])
    if any(read_regular(path) != raw for path, raw in snapshots.items()):
        raise ValueError(f"Installation changed during preview; retry; recovery: {recovery}")
    written = []
    try:
        for path in changes:
            atomic_write(path, replacements[path].decode("utf-8"))
            written.append(path)
        atomic_write(manifest_path, json.dumps(manifest, indent=2))
    except (OSError, ValueError) as error:
        try:
            for path in reversed(written):
                atomic_write(path, snapshots[path].decode("utf-8"))
        except OSError as rollback_error:
            raise OSError(
                f"Upgrade and rollback failed; recovery files: {recovery}"
            ) from rollback_error
        raise OSError(f"Upgrade failed; previous files restored; recovery: {recovery}") from error
    return {
        **result,
        "status": "upgraded",
        "applied": True,
        "restart_required": True,
        "recovery": str(recovery),
    }


def uninstall(config_path):
    config = load_config(config_path)
    if config["scope"] != "personal":
        raise ValueError("This integration manages personal scope only")
    manifest_path = Path(config["state_path"]) / "install-manifest.json"
    if not manifest_path.exists():
        return {"status": "not installed"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    modified = []
    for entry in manifest["entries"]:
        path = Path(entry["path"])
        raw = path.read_bytes()
        current = raw.decode("utf-8-sig").replace("\r\n", "\n")
        if checksum(raw) == entry["after"]:
            path.write_bytes(Path(entry["backup"]).read_bytes())
        elif current.count(entry["block"]) == 1:
            atomic_write(path, current.replace(entry["block"], "", 1))
        elif BEGIN in current:
            modified.append(str(path))
    skill = Path(manifest["skill"])
    if skill.exists():
        if checksum(skill.read_bytes()) == manifest["skill_hash"]:
            skill.unlink()
        else:
            modified.append(str(skill))
    if modified:
        return {"status": "manual reconciliation needed", "modified_owned_files": modified}
    manifest_path.rename(manifest_path.with_name(f"uninstalled-{uuid.uuid4().hex}.json"))
    return {"status": "uninstalled", "notes": "preserved"}
