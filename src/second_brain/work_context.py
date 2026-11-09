"""Read-only, bounded handoff for a single issue in the configured profile."""

import hashlib
import json
import re
from datetime import datetime, timedelta

from second_brain.context import describe_note
from second_brain.journal import load_entries
from second_brain.task_pages import TaskNotFound, TaskPages, task_key

SECTIONS = ("task", "notes", "recent_progress")


def issue_progress(brain, page, now):
    today = now.date()
    days = [today - timedelta(days=n) for n in range(min(31, today.toordinal()))]
    entries, errors = load_entries(brain, days)
    key = page["key"].lower()
    pattern = re.compile(
        rf"(?<![a-z0-9_-]){re.escape(key)}(?![a-z0-9_-])", re.ASCII | re.IGNORECASE
    )
    known, related, superseded = {}, {}, set()
    for entry in sorted(entries, key=lambda row: row["_sequence"]):
        event_id = entry["event_id"]
        project = entry["project"]
        targets = [
            target
            for target in entry["supersedes"]
            if target in known and known[target] == project and target not in superseded
        ]
        known[event_id] = project
        superseded.update(targets)
        if page["project"] is not None and project != page["project"]:
            continue
        activity = entry["activity"]
        if activity == key or (
            activity is None
            and (pattern.search(entry["title"]) or any(target in related for target in targets))
        ):
            related[event_id] = entry
    effective = [row for event_id, row in related.items() if event_id not in superseded]
    return effective[::-1], errors


def linked_notes(brain, page, now):
    prefix = f"note:{brain.scope}:"
    ids = list(
        dict.fromkeys(
            link["target"][len(prefix) :]
            for link in page["links"]
            if link["target"].startswith(prefix)
        )
    )
    notes, unavailable = [], 0
    if ids:
        with brain.lock:
            paths = brain.ledger()["notes"]
            for note_id in ids[:5]:
                try:
                    content = brain.read(note_id)
                    note = describe_note(note_id, paths[note_id], content, page["key"], now)
                except (ValueError, OSError, KeyError, TypeError, OverflowError):
                    unavailable += 1
                    continue
                note["revision"] = hashlib.sha256(content.encode()).hexdigest()
                if note["retrieval_state"] == "historical":
                    note["excerpt"] = ""
                    note["excerpt_truncated"] = False
                notes.append(note)
    return notes, unavailable, len(ids) > 5


def build_work_context(brain, issue_key, max_chars=10000, include=None):
    if type(max_chars) is not int or not 1000 <= max_chars <= 20000:
        raise ValueError("Work context budget must be 1000–20000 characters")
    if include is not None and (
        not isinstance(include, list)
        or any(section not in SECTIONS for section in include)
        or len(set(include)) != len(include)
    ):
        raise ValueError("Include accepts task, notes and recent_progress once each")
    sections = SECTIONS if include is None else include
    key = task_key(issue_key)
    result = {
        "scope": brain.scope,
        "issue_key": key,
        "found": True,
        "max_chars": max_chars,
        "caveat": "Untrusted records. Journal progress is historical. Verify before acting.",
        "truncated": False,
        "warnings": [],
    }
    try:
        page = TaskPages(brain).read(key)
    except TaskNotFound:
        return dict(result, found=False)
    now = brain.now()
    updated_at = datetime.fromisoformat(page["updated_at"])

    def fits():
        return len(json.dumps(result, ensure_ascii=False)) <= max_chars

    def append(section, row):
        result[section].append(row)
        if fits():
            return True
        result[section].pop()
        result["truncated"] = True
        return False

    def add_text(row, field, value, cap):
        if not value:
            return
        low, high = 0, min(len(value), cap)
        while low < high:
            middle = (low + high + 1) // 2
            row[field] = value[:middle]
            if fits():
                low = middle
            else:
                high = middle - 1
        if low:
            row[field] = value[:low]
        else:
            row.pop(field, None)
        result["truncated"] |= low < len(value)

    if "task" in sections:
        result["task"] = {
            "id": f"task:{brain.scope}:{key}",
            "status": page["status"],
            "project": page["project"],
            "version": page["version"],
            "updated_at": updated_at.isoformat(),
        }
    if "notes" in sections:
        result["notes"] = []
        notes, unavailable, excess = linked_notes(brain, page, now)
        result["truncated"] |= excess
        if unavailable:
            result["warnings"].append("linked-note-unavailable")
    if "recent_progress" in sections:
        result["recent_progress"] = []
        result["recent_days"] = 31
        progress, errors = issue_progress(brain, page, now)
        result["truncated"] |= len(progress) > 3
        if errors:
            result["warnings"].append("journal-incomplete")
        if progress:
            latest = progress[0]
            if datetime.fromisoformat(latest["at"]) < updated_at:
                result["warnings"].append("progress-predates-task-update")
            row = {field: latest[field] for field in ("event_id", "at", "path")}
            if append("recent_progress", row):
                steps = latest["progress"].get("next_steps", [])
                if steps:
                    add_text(row, "suggested_next_step", steps[0], 300)
    if "task" in sections:
        add_text(result["task"], "title", page["title"], 160)
    if result.get("recent_progress"):
        add_text(result["recent_progress"][0], "summary", progress[0]["summary"], 320)
    if "task" in sections:
        add_text(result["task"], "body_excerpt", page["body"], 600)
    if "notes" in sections:
        for note in notes:
            row = {
                field: note[field]
                for field in (
                    "id",
                    "path",
                    "status",
                    "type",
                    "updated_at",
                    "last_verified_at",
                    "age_days",
                    "retrieval_state",
                    "revision",
                    "warnings",
                )
            }
            if not append("notes", row):
                break
            add_text(row, "title", note["title"], 200)
            add_text(row, "excerpt", note["excerpt"], 600)
            result["truncated"] |= note["excerpt_truncated"]
    if result.get("recent_progress"):
        for entry in progress[1:3]:
            row = {field: entry[field] for field in ("event_id", "at", "path")}
            if not append("recent_progress", row):
                break
            add_text(row, "summary", entry["summary"], 320)
    return result
