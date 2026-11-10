"""Coordinate an explicit issue checkpoint using the existing store writers."""

import hashlib
import json
import re
from datetime import datetime

from filelock import Timeout

from second_brain.agent_log import AgentLog, capture_block_reason, validate_event
from second_brain.core import (
    PENDING_CHECKPOINT,
    SLUG,
    TYPES,
    atomic_write,
    parse_note,
    safe_text,
    scoped_path,
    validate_candidate,
)
from second_brain.journal import MAX_DAY_BYTES, load_entries
from second_brain.task_pages import MAX_EVENTS, STATES, TaskPages, task_key
from second_brain.workflow import check_capture, metadata as journal_metadata

REQUIRED = {"scope", "issue_key", "event_id", "expected_version", "source_agent", "summary"}
OPTIONAL = {"status", "progress", "knowledge", "agent_action"}
INSPECTION_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, Timeout)


def decode_plan(raw, scope):
    if len(raw) > 2048:
        raise ValueError("Checkpoint intent exceeds its size limit")
    plan = json.loads(raw)
    if (
        not isinstance(plan, dict)
        or set(plan) != {"schema_version", "scope", "key", "event_id", "at", "fingerprint", "log"}
        or type(plan["schema_version"]) is not int
        or plan["schema_version"] != 1
        or plan["scope"] != scope
        or plan["key"] != task_key(plan["key"])
        or not SLUG.fullmatch(safe_text(plan["event_id"], 100))
        or not re.fullmatch(r"[0-9a-f]{64}", safe_text(plan["fingerprint"], 64))
        or datetime.fromisoformat(safe_text(plan["at"], 64)).tzinfo is None
        or type(plan["log"]) is not bool
    ):
        raise ValueError("Invalid checkpoint intent")
    return plan


def read_plan(brain):
    path = scoped_path(brain.state, PENDING_CHECKPOINT)
    try:
        with path.open("rb") as stream:
            return decode_plan(stream.read(2049), brain.scope)
    except FileNotFoundError:
        return None


def _capture_state(brain, plan, journal_path):
    ledger = brain.ledger()
    events = ledger["events"]
    if plan["event_id"] not in events:
        # The legacy intent does not identify a potential note until the ledger reserves it.
        return "absent", "indeterminate"
    event = events[plan["event_id"]]
    if (
        event["at"] != plan["at"]
        or event["status"] not in {"pending", "committed"}
        or not re.fullmatch(r"[0-9a-f]{64}", event["fingerprint"])
    ):
        raise ValueError("Capture record does not match checkpoint intent")
    relative = event["path"]
    if relative == journal_path:
        return event["status"], "not-required"
    note = re.fullmatch(r"([a-z-]+)/([a-z0-9][a-z0-9-]{0,99})\.md", relative)
    if not note or note[1] not in TYPES.values():
        raise ValueError("Invalid checkpoint note path")
    if event["status"] == "committed" and ledger["notes"].get(note[2]) != relative:
        return event["status"], "indeterminate"
    try:
        with brain.path(relative).open(encoding="utf-8") as stream:
            metadata, _, _ = parse_note(stream.read(100001), note[2], brain.scope)
        if datetime.fromisoformat(str(metadata["created_at"])) != datetime.fromisoformat(
            plan["at"]
        ):
            return event["status"], "indeterminate"
    except FileNotFoundError:
        return event["status"], "absent" if event["status"] == "pending" else "indeterminate"
    except INSPECTION_ERRORS:
        return event["status"], "indeterminate"
    return event["status"], "present"


def _receipt_state(brain, plan):
    data = TaskPages(brain).export()
    page = next((row for row in data["items"] if row["key"] == plan["key"]), None)
    if page is None:
        return "indeterminate"
    receipt = data.get("events", {}).get(plan["event_id"])
    if receipt is None:
        return "absent"
    checkpoint = page.get("checkpoint", {})
    if (
        "checkpoint" in receipt
        and receipt["key"] == plan["key"]
        and receipt["fingerprint"] == plan["fingerprint"]
        and receipt["version"] == page["version"]
        and checkpoint.get("event_id") == plan["event_id"]
        and checkpoint.get("at") == plan["at"]
    ):
        return "present"
    return "indeterminate"


def _log_state(brain, plan):
    if not plan["log"]:
        return "not-required"
    if not scoped_path(brain.state, "agent-log.json").is_file():
        return "indeterminate"
    row = next(
        (
            item
            for item in AgentLog(brain).export()["items"]
            if item["event_id"] == plan["event_id"]
        ),
        None,
    )
    if row is None:
        return "absent"
    refs = {(ref["kind"], ref["target"]) for ref in row["references"]}
    if row["recorded_at"] == plan["at"] and {
        ("content", f"task:{brain.scope}:{plan['key']}"),
        ("journal-event", plan["event_id"]),
    }.issubset(refs):
        return "present"
    return "indeterminate"


def diagnose_checkpoint(brain):
    """Describe one pending operation without returning the candidate or changing stores."""
    result = {"scope": brain.scope}
    try:
        with brain.lock:
            try:
                plan = read_plan(brain)
            except INSPECTION_ERRORS:
                return dict(result, status="unavailable", reason="checkpoint-intent-unavailable")
            if plan is None:
                return dict(result, status="clear")
            day = datetime.fromisoformat(plan["at"]).date()
            result.update(
                status="pending",
                event_id=plan["event_id"],
                issue_key=plan["key"],
                at=plan["at"],
                next_step="retry-original-candidate-or-inspect-a-separate-recovery-copy",
            )
            try:
                result["capture_ledger"], result["note"] = _capture_state(
                    brain, plan, f"journal/{day:%Y}/{day:%Y-%m-%d}.md"
                )
            except INSPECTION_ERRORS:
                result.update(capture_ledger="indeterminate", note="indeterminate")
            try:
                entries, errors = load_entries(brain, [day], pending_event_id=plan["event_id"])
                entry = next((row for row in entries if row["event_id"] == plan["event_id"]), None)
                if (
                    errors
                    or result["capture_ledger"] == "indeterminate"
                    or (
                        entry
                        and (
                            not entry["structured"]
                            or entry["at"] != plan["at"]
                            or entry["title"] != f"Checkpoint {plan['key']}"
                        )
                    )
                ):
                    result["journal"] = "indeterminate"
                else:
                    result["journal"] = "present" if entry else "absent"
            except INSPECTION_ERRORS:
                result["journal"] = "indeterminate"
            for field, inspect in (("task_receipt", _receipt_state), ("agent_log", _log_state)):
                try:
                    result[field] = inspect(brain, plan)
                except INSPECTION_ERRORS:
                    result[field] = "indeterminate"
            return result
    except Timeout:
        return dict(result, status="unavailable", reason="profile-busy")


def capture_payload(brain, page, candidate):
    knowledge = candidate.get("knowledge")
    payload = {
        "scope": brain.scope,
        "mode": "journal-only",
        "event_id": candidate["event_id"],
        "title": f"Checkpoint {page['key']}",
        "source_agent": candidate["source_agent"],
        "summary": candidate["summary"],
        "project": page["project"],
        "progress": candidate.get("progress", {}),
    }
    if page["project"]:
        payload["activity"] = page["key"].lower()
    if knowledge is not None:
        required = {"id", "title", "type", "status", "body"}
        if (
            not isinstance(knowledge, dict)
            or not required
            <= set(knowledge)
            <= required | {"evidence", "tags", "related", "source_refs"}
            or knowledge["status"] not in ("verified", "unverified", "draft")
        ):
            raise ValueError("Provide a reviewed new note using the documented knowledge fields")
        payload.update(knowledge, mode="note")
    validate_candidate(payload, brain.scope)
    return payload


def action_payload(brain, page, candidate):
    action = candidate.get("agent_action")
    if action is None:
        return None
    timezone = brain.config["timezone"]
    action = validate_event(action, brain.scope, timezone)
    if (
        action["event_id"] != candidate["event_id"]
        or action["agent"] != candidate["source_agent"]
        or action["project"] != page["project"]
    ):
        raise ValueError("Agent action must use the checkpoint event, agent and task project")
    refs = action["references"]
    links = [
        {"kind": "content", "target": f"task:{brain.scope}:{page['key']}", "label": page["key"]},
        {"kind": "journal-event", "target": action["event_id"], "label": "Checkpoint"},
    ]
    for link in links:
        if not any((ref["kind"], ref["target"]) == (link["kind"], link["target"]) for ref in refs):
            refs = [*refs, link]
    return validate_event(dict(action, references=refs), brain.scope, timezone)


def check_journal_room(brain, payload, at):
    day = at.date()
    _, errors = load_entries(brain, [day])
    if errors:
        raise ValueError("Checkpoint journal is unavailable")
    path = brain.path(f"journal/{day:%Y}/{day:%Y-%m-%d}.md")
    size = path.stat().st_size if path.exists() else 0
    structured = json.dumps(journal_metadata(payload), ensure_ascii=True).replace(">", "\\u003e")
    prose = json.dumps([payload["summary"], payload["progress"]], ensure_ascii=True)
    # Reserve room for the rendered marker, headings, note link and indented progress.
    if size + len(structured) + 2 * len(prose) + 1024 > MAX_DAY_BYTES:
        raise ValueError("Checkpoint journal has insufficient space")


def prepare_task(data, page, payload, candidate, plan):
    events = data.get("events", {})
    if len(events) >= MAX_EVENTS:
        raise ValueError("Task event limit reached")
    next_steps = payload["progress"].get("next_steps", [])
    item = dict(
        page,
        version=page["version"] + 1,
        status=candidate.get("status", page["status"]),
        updated_at=plan["at"],
        checkpoint={
            "event_id": plan["event_id"],
            "at": plan["at"],
            "summary": payload["summary"].strip(),
            "next_step": next_steps[0] if next_steps else None,
        },
    )
    note_id = payload.get("id")
    if note_id:
        target = f"note:{plan['scope']}:{note_id}"
        if not any(
            link["target"] == target and link["annotation_id"] is None for link in item["links"]
        ):
            item["links"] = [
                *item["links"],
                {"target": target, "annotation_id": None, "label": payload["title"].strip()[:160]},
            ]
    receipt = {
        "fingerprint": plan["fingerprint"],
        "key": plan["key"],
        "version": item["version"],
        "checkpoint": {"note_id": note_id, "agent_log": False},
    }
    return dict(
        data,
        schema_version=3,
        items=[item if row["key"] == plan["key"] else row for row in data["items"]],
        events={**events, plan["event_id"]: receipt},
    ), receipt


def record_checkpoint(brain, candidate):
    if (
        not isinstance(candidate, dict)
        or not REQUIRED <= set(candidate) <= REQUIRED | OPTIONAL
        or candidate["scope"] != brain.scope
    ):
        raise ValueError("Checkpoint requires documented fields and the configured scope")
    key = task_key(candidate["issue_key"])
    event_id = safe_text(candidate["event_id"], 100)
    version = candidate["expected_version"]
    if not SLUG.fullmatch(event_id) or type(version) is not int or not 1 <= version < 1_000_000:
        raise ValueError("Checkpoint requires an event ID and an existing task version")
    if "status" in candidate and candidate["status"] not in tuple(STATES):
        raise ValueError("Invalid checkpoint task status")
    fingerprint = hashlib.sha256(
        json.dumps(dict(candidate, issue_key=key), sort_keys=True).encode()
    ).hexdigest()
    result = {"event_id": event_id, "issue_key": key}
    with brain.lock:
        tasks = TaskPages(brain)
        data = tasks.export()
        path = scoped_path(brain.state, PENDING_CHECKPOINT)
        plan = read_plan(brain)
        if (
            plan
            and plan["event_id"] == event_id
            and (plan["fingerprint"] != fingerprint or plan["key"] != key)
        ):
            return dict(result, status="conflict", reason="event-id-reused")
        previous = data.get("events", {}).get(event_id)
        if previous:
            if previous["fingerprint"] != fingerprint or "checkpoint" not in previous:
                return dict(result, status="conflict", reason="event-id-reused")
            if plan and plan["event_id"] == event_id:
                path.unlink(missing_ok=True)
            return dict(
                result, status="duplicate", version=previous["version"], **previous["checkpoint"]
            )
        if plan and plan["event_id"] != event_id:
            return dict(
                result,
                status="blocked",
                reason="pending-checkpoint",
                pending_event_id=plan["event_id"],
            )
        if scoped_path(brain.state, "paused").exists():
            return dict(result, status="blocked", reason="paused")
        page = next((row for row in data["items"] if row["key"] == key), None)
        if page is None or page["version"] != version:
            return dict(
                result,
                status="conflict",
                reason="version-mismatch",
                version=page["version"] if page else 0,
            )

        payload = capture_payload(brain, page, candidate)
        action = action_payload(brain, page, candidate)
        log = AgentLog(brain) if action else None
        new_plan = plan is None
        if new_plan:
            ledger = brain.ledger()
            if event_id in ledger["events"]:
                return dict(result, status="conflict", reason="event-id-reused")
            if any(row["status"] != "committed" for row in ledger["events"].values()):
                return dict(result, status="blocked", reason="pending-captures")
            note_id = payload.get("id")
            if note_id and (
                note_id in ledger["notes"]
                or any(
                    brain.path(f"{folder}/{note_id}.md").exists() for folder in set(TYPES.values())
                )
            ):
                return dict(result, status="conflict", reason="knowledge-id-already-exists")
            check_capture(brain, payload, dedupe_activity=False)
            now = brain.now()
            check_journal_room(brain, payload, now)
            at = now.isoformat(timespec="seconds")
            log_data = log.export() if log else None
            log_enabled = (
                log_data is not None and capture_block_reason(log_data, action, now) is None
            )
            if log_enabled:
                log_data["items"].append(dict(action, recorded_at=at))
                log._serialize(log_data)
            plan = dict(
                schema_version=1,
                scope=brain.scope,
                key=key,
                event_id=event_id,
                fingerprint=fingerprint,
                at=at,
                log=log_enabled,
            )
        if plan["log"] and log is None:
            raise ValueError("Checkpoint intent requires its original Agent Log action")
        next_data, receipt = prepare_task(data, page, payload, candidate, plan)
        tasks._serialize(next_data)
        if new_plan:
            atomic_write(path, json.dumps(plan))

        pending = dict(result, status="pending", reason="retry-identical-checkpoint")
        try:
            capture = brain.capture(payload, checkpoint=plan)
            if capture["status"] not in ("saved", "duplicate"):
                return pending
            if plan["log"]:
                logged = log.record(action, checkpoint_at=plan["at"])
                receipt["checkpoint"]["agent_log"] = logged["status"] in ("saved", "duplicate")
            with tasks.lock:
                tasks._write(next_data)
            path.unlink()
        except (OSError, Timeout, ValueError):
            return pending
        return dict(result, status="saved", version=receipt["version"], **receipt["checkpoint"])
