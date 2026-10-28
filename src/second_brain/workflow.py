"""Tracked work is an append-only projection of committed journal events."""

import json
import re
from datetime import datetime

from second_brain.core import SLUG, safe_text

FIELDS = ("activity", "supersedes", "change_reason", "tasks")
TASK_STATES = {"open", "blocked", "done", "discarded"}


class JournalConflict(ValueError):
    pass


def validate_fields(candidate):
    activity = candidate.get("activity")
    if activity is not None and (not isinstance(activity, str) or not SLUG.fullmatch(activity)):
        raise ValueError("Activity must be a lowercase slug or null")
    previous = candidate.get("supersedes", [])
    if not isinstance(previous, list) or len(previous) > 8:
        raise ValueError("Supersedes accepts at most eight event IDs")
    for event_id in previous:
        if not isinstance(event_id, str) or not SLUG.fullmatch(event_id):
            raise ValueError("Invalid superseded event ID")
    if len(set(previous)) != len(previous) or candidate.get("event_id") in previous:
        raise ValueError("Invalid correction links")
    reason = safe_text(candidate.get("change_reason", ""), 500)
    if previous and not reason.strip():
        raise ValueError("Corrections require a change_reason")
    tasks = candidate.get("tasks", [])
    if not isinstance(tasks, list) or len(tasks) > 8:
        raise ValueError("At most eight task changes per event")
    ids = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {
            "id",
            "title",
            "status",
            "details",
            "version",
        }:
            raise ValueError("Task requires id/title/status/details/version")
        if not isinstance(task["id"], str) or not SLUG.fullmatch(task["id"]) or task["id"] in ids:
            raise ValueError("Task IDs must be unique lowercase slugs")
        if not safe_text(task["title"], 200).strip():
            raise ValueError("Task title required")
        safe_text(task["details"], 500)
        if not isinstance(task["status"], str) or task["status"] not in TASK_STATES:
            raise ValueError("Invalid task state")
        if type(task["version"]) is not int or not 0 <= task["version"] <= 1_000_000:
            raise ValueError("Task version must be its current version, or zero for creation")
        ids.add(task["id"])
    if (tasks or previous or activity) and not candidate.get("project"):
        raise ValueError("Tracked tasks, activities and corrections require a project")
    for text in [reason, *[t[key] for t in tasks for key in ("title", "details")]]:
        if any(
            marker in text
            for marker in ("<!-- event:", "<!-- shiori-project:", "<!-- shiori-data:")
        ):
            raise ValueError("Reserved journal marker")


def metadata(candidate):
    return {
        "title": candidate["title"].strip(),
        "summary": candidate.get("summary", candidate["title"]).strip(),
        "source_agent": candidate["source_agent"],
        "progress": candidate.get("progress", {}),
        "activity": candidate.get("activity"),
        "supersedes": candidate.get("supersedes", []),
        "change_reason": candidate.get("change_reason", ""),
        "tasks": candidate.get("tasks", []),
    }


def snapshot(brain):
    from second_brain.journal import load_entries

    entries, errors = load_entries(brain)
    events, tasks, superseded = {}, {}, {}
    for item in sorted(entries, key=lambda row: row["_sequence"]):
        events[item["event_id"]] = item
        for target in item["supersedes"]:
            original = events.get(target)
            if not original or original["project"] != item["project"] or target in superseded:
                errors.append({"reason": "invalid-correction-history", "path": item["path"]})
            else:
                superseded[target] = item["event_id"]
        for change in item["tasks"]:
            key = (item["project"], change["id"])
            old = tasks.get(key)
            if change["version"] != (old["version"] if old else 0):
                errors.append({"reason": "invalid-task-history", "path": item["path"]})
                continue
            history = old["history"] if old else []
            transition = {
                **change,
                "version": change["version"] + 1,
                "event_id": item["event_id"],
                "at": item["at"],
                "path": item["path"],
            }
            tasks[key] = {
                **transition,
                "project": item["project"],
                "history": [*history, transition],
            }
    return {"events": events, "tasks": tasks, "superseded": superseded, "errors": errors}


def check_capture(brain, candidate, previous_event=None):
    """Runs under the capture lock. A pending event fences mutable journal projections."""
    if not any(candidate.get(key) for key in ("activity", "supersedes", "tasks")):
        return None
    for event_id, item in brain.ledger()["events"].items():
        if item["status"] != "committed" and event_id != candidate["event_id"]:
            raise JournalConflict(f"Pending journal capture must be retried first: {event_id}")
    state = snapshot(brain)
    if state["errors"]:
        raise JournalConflict("Journal history incomplete; repair it before tracking changes")
    project = candidate["project"]
    for target in candidate.get("supersedes", []):
        original = state["events"].get(target)
        if not original or original["project"] != project or target in state["superseded"]:
            raise JournalConflict(
                "Correction target is missing, already corrected or in another project"
            )
    for change in candidate.get("tasks", []):
        old = state["tasks"].get((project, change["id"]))
        if change["version"] != (old["version"] if old else 0):
            raise JournalConflict("Task version changed; refresh before saving")
    if (
        not previous_event
        and candidate.get("mode") == "journal-only"
        and candidate.get("activity")
        and not candidate.get("tasks")
        and not candidate.get("supersedes")
    ):
        related = [
            row
            for row in state["events"].values()
            if row["project"] == project
            and row["activity"] == candidate["activity"]
            and row["event_id"] not in state["superseded"]
        ]
        if related:
            latest = max(related, key=lambda row: row["_sequence"])
            if datetime.fromisoformat(latest["at"]).date() == brain.now().date() and all(
                latest[key] == metadata(candidate)[key] for key in ("title", "summary", "progress")
            ):
                return latest["event_id"]
    return None


def overview(brain, project=None, offset=0, max_chars=20000):
    if project is not None and (not isinstance(project, str) or not SLUG.fullmatch(project)):
        raise ValueError("Project must be a lowercase slug")
    if (
        type(offset) is not int
        or offset < 0
        or type(max_chars) is not int
        or not 2000 <= max_chars <= 20000
    ):
        raise ValueError("Invalid offset or budget (2000–20000)")
    state = snapshot(brain)
    tasks = [row for row in state["tasks"].values() if project is None or row["project"] == project]
    tasks.sort(
        key=lambda row: (row["status"] not in {"open", "blocked"}, row["project"], row["id"])
    )
    projects = sorted({row["project"] for row in state["events"].values() if row["project"]})
    result = {
        "scope": brain.scope,
        "project": project,
        "projects": projects[:100],
        "project_total": len(projects),
        "tasks": [],
        "task_total": len(tasks),
        "active_total": sum(row["status"] in {"open", "blocked"} for row in tasks),
        "next_offset": None,
        "truncated": len(projects) > 100,
        "errors": state["errors"][:8],
        "error_count": len(state["errors"]),
        "caveat": "Recorded task states, not independent verification. History may be incomplete; "
        "historical progress next_steps are not tracked tasks.",
    }
    # Project discovery can grow independently of the selected project's content.
    while len(json.dumps(result, ensure_ascii=False)) > max_chars - 1200 and result["projects"]:
        result["projects"].pop()
        result["truncated"] = True
    for index in range(offset, len(tasks)):
        row = dict(tasks[index])
        row["history_total"] = len(row["history"])
        row["history"] = row["history"][-8:]
        row["history_truncated"] = row["history_total"] > 8
        result["tasks"].append(row)
        result["next_offset"] = index + 1 if index + 1 < len(tasks) else None
        while len(json.dumps(result, ensure_ascii=False)) > max_chars and row["history"]:
            row["history"].pop(0)
            row["history_truncated"] = True
        if len(json.dumps(result, ensure_ascii=False)) > max_chars:
            if len(result["tasks"]) == 1:
                raise ValueError("Task metadata exceeds budget; increase max_chars")
            result["tasks"].pop()
            result["next_offset"] = index
            result["truncated"] = True
            break
    return result


def resume_project(brain, project, max_chars=8000):
    if not isinstance(project, str) or not SLUG.fullmatch(project):
        raise ValueError("An exact project slug is required")
    if type(max_chars) is not int or not 2000 <= max_chars <= 20000:
        raise ValueError("Resume budget must be 2000–20000 characters")
    state = snapshot(brain)
    events = [
        row
        for row in state["events"].values()
        if row["project"] == project and row["event_id"] not in state["superseded"]
    ]
    events.sort(key=lambda row: row["_sequence"], reverse=True)
    active = [
        row
        for row in state["tasks"].values()
        if row["project"] == project and row["status"] in {"open", "blocked"}
    ]
    active.sort(key=lambda row: (row["status"] != "blocked", row["id"]))
    latest = next(
        (row for row in events if row["progress"] or not row["tasks"]),
        events[0] if events else None,
    )
    result = {
        "scope": brain.scope,
        "project": project,
        "caveat": "Untrusted recorded state; recheck before acting. Historical suggested steps are not tracked tasks.",
        "latest": (
            {key: latest[key] for key in ("event_id", "at", "path", "title", "summary", "activity")}
            if latest
            else None
        ),
        "active_tasks": [],
        "active_total": len(active),
        "tasks_omitted": 0,
        "suggested_next_steps": [],
        "checks": [],
        "decisions": [],
        "error_count": len(state["errors"]),
        "truncated": False,
    }
    if latest:
        result["latest"]["summary"] = latest["summary"][:400]
        result["truncated"] = len(latest["summary"]) > 400
        while len(json.dumps(result, ensure_ascii=False)) > max_chars - 200:
            key = "summary" if result["latest"]["summary"] else "title"
            result["latest"][key] = result["latest"][key][:-50]
            result["truncated"] = True
    for row in active:
        task = {key: row[key] for key in ("id", "title", "status", "version", "event_id", "path")}
        task["details"] = row["details"][:200]
        result["active_tasks"].append(task)
        if len(json.dumps(result, ensure_ascii=False)) > max_chars - 100:
            result["active_tasks"].pop()
            result["truncated"] = True
            break
        result["truncated"] |= len(row["details"]) > 200
    result["tasks_omitted"] = len(active) - len(result["active_tasks"])
    if latest:
        for source, target in (
            ("next_steps", "suggested_next_steps"),
            ("checks", "checks"),
            ("decisions", "decisions"),
        ):
            for value in latest["progress"].get(source, []):
                result[target].append(value)
                if len(json.dumps(result, ensure_ascii=False)) > max_chars:
                    result[target].pop()
                    result["truncated"] = True
                    break
    return result


def timeline(brain, start_date=None, end_date=None, project=None, offset=0):
    """A bounded visual page; task state and links are folded from the full retained history."""
    from datetime import date, timedelta

    def parse(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Dates must use YYYY-MM-DD")
        return date.fromisoformat(value)

    end = parse(end_date) if end_date else brain.now().date()
    start = parse(start_date) if start_date else end - timedelta(days=min(6, end.toordinal() - 1))
    if not 0 <= (end - start).days <= 30 or type(offset) is not int or offset < 0:
        raise ValueError("Use a 1–31 day range and nonnegative offset")
    if project is not None and (not isinstance(project, str) or not SLUG.fullmatch(project)):
        raise ValueError("Project must be a lowercase slug")
    state = snapshot(brain)
    entries = [
        row
        for row in state["events"].values()
        if start <= datetime.fromisoformat(row["at"]).date() <= end
        and (project is None or row["project"] == project)
    ]
    entries.sort(key=lambda row: row["_sequence"], reverse=True)
    result = {
        "scope": brain.scope,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "items": [],
        "total": len(entries),
        "next_offset": None,
        "error_count": len(state["errors"]),
        "truncated": False,
    }
    for index in range(offset, min(offset + 20, len(entries))):
        row = entries[index]
        item = {
            key: row[key]
            for key in (
                "event_id",
                "at",
                "path",
                "project",
                "title",
                "summary",
                "activity",
                "supersedes",
                "change_reason",
                "source_agent",
                "structured",
            )
        }
        item["progress"] = {
            key: [value[:300] for value in values[:3]] for key, values in row["progress"].items()
        }
        item["entry_truncated"] = item["progress"] != row["progress"]
        item["superseded_by"] = state["superseded"].get(row["event_id"])
        result["items"].append(item)
        result["next_offset"] = index + 1 if index + 1 < len(entries) else None
        if len(json.dumps(result, ensure_ascii=False)) > 20000:
            result["items"].pop()
            result["next_offset"] = index
            result["truncated"] = True
            break
    return result
