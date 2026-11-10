"""Local, explicitly confirmed recovery of a verifiable checkpoint intent."""

import hashlib
import json

from second_brain.backup import MAX_FILES, backup, read_bundle
from second_brain.checkpoints import INSPECTION_ERRORS, diagnose_checkpoint, read_plan
from second_brain.core import PENDING_CHECKPOINT, TYPES, scoped_path
from second_brain.task_pages import TaskPages


def _no_untracked_notes(brain, ledger):
    registered = set(ledger["notes"].values())
    events = ledger["events"].values()
    # Note creation always has a durable capture event before writing to the vault.
    if any(event["status"] != "committed" for event in events) or not registered.issubset(
        event["path"] for event in events
    ):
        return False
    count = 0
    for folder in set(TYPES.values()):
        try:
            for path in brain.path(folder).iterdir():
                count += 1
                if count > MAX_FILES or f"{folder}/{path.name}" not in registered:
                    return False
        except FileNotFoundError:
            continue
    return True


def _action(brain, plan, report, receipt):
    ledger = brain.ledger()
    if report["capture_ledger"] == report["journal"] == "absent" and (
        report["task_receipt"] in {"absent", "abandoned"}
        and report["agent_log"] in {"absent", "not-required"}
        and _no_untracked_notes(brain, ledger)
    ):
        return "abandon"
    if (
        report["task_receipt"] == report["journal"] == "present"
        and report["capture_ledger"] == "committed"
    ):
        checkpoint = receipt["checkpoint"]
        note_id = checkpoint["note_id"]
        if note_id is None:
            note_matches = report["note"] == "not-required"
        else:
            note_matches = (
                report["note"] == "present"
                and ledger["notes"].get(note_id) == ledger["events"][plan["event_id"]]["path"]
            )
        log_matches = (
            report["agent_log"] == "present"
            if checkpoint["agent_log"]
            else report["agent_log"] in {"not-required", "absent"}
        )
        if note_matches and log_matches:
            return "finalize"
    return None


def _preview(brain, tasks):
    report = diagnose_checkpoint(brain)
    if report["status"] != "pending":
        return report, None
    plan = read_plan(brain)
    data = tasks.export()
    page = next((item for item in data["items"] if item["key"] == plan["key"]), None)
    events = data.get("events", {})
    receipt = events.get(plan["event_id"])
    action = _action(brain, plan, report, receipt) if page else None
    if action is None:
        return dict(report, status="blocked", reason="effects-incomplete-or-unverified"), None
    snapshot = [str(brain.vault), str(brain.state), plan, report, page["version"], receipt, action]
    revision = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    result = dict(report, status="ready", action=action, revision=revision, backup_required=True)
    if receipt and "resolution" in receipt:
        return result, None
    resolved = dict(
        receipt
        or {"key": plan["key"], "version": page["version"], "fingerprint": plan["fingerprint"]},
        resolution={"action": action, "at": brain.now().isoformat(timespec="seconds")},
    )
    return result, dict(data, schema_version=4, events={**events, plan["event_id"]: resolved})


def resolve_checkpoint(brain, *, apply=False, expect_revision=None, backup_path=None):
    if apply and (not expect_revision or backup_path is None):
        raise ValueError("Confirmation requires --expect-revision and --backup")
    fallback = {"scope": brain.scope, "status": "unavailable"}
    try:
        with brain.lock:
            tasks = TaskPages(brain)
            preview, updated = _preview(brain, tasks)
            if preview["status"] != "ready" or not apply:
                return preview
            if preview["revision"] != expect_revision:
                return dict(preview, status="blocked", reason="preview-changed")
            if updated is not None:
                tasks._serialize(updated)
            try:
                backup(brain, backup_path)
                read_bundle(backup_path, brain.scope)
            except INSPECTION_ERRORS:
                return dict(preview, status="blocked", reason="recovery-copy-failed")
            current, updated = _preview(brain, tasks)
            if current.get("revision") != expect_revision:
                return dict(current, status="blocked", reason="preview-changed", backup_saved=True)
            try:
                if updated is not None:
                    with tasks.lock:
                        tasks._write(updated)
                scoped_path(brain.state, PENDING_CHECKPOINT).unlink()
            except INSPECTION_ERRORS:
                return dict(
                    current, status="blocked", reason="resolution-interrupted", backup_saved=True
                )
            return dict(current, status="resolved", backup_saved=True)
    except INSPECTION_ERRORS:
        return dict(fallback, reason="checkpoint-state-unavailable")
