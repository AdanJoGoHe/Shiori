"""Opt-in, reported actions, separate from canonical knowledge and progress captures."""

import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from filelock import FileLock

from second_brain.annotations import Conflict
from second_brain.core import AGENTS, PENDING_CHECKPOINT, SLUG, atomic_write, safe_text, scoped_path
from second_brain.task_pages import validate_link

MAX_BYTES = 8_000_000
MAX_EVENTS = 10_000
KINDS = {
    "command-proposed",
    "command-attempted",
    "command-executed",
    "check",
    "file-changed",
    "link-found",
    "page-visited",
}
OUTCOMES = {"success", "failure", "cancelled", "unknown"}
FIELDS = {
    "schema_version",
    "scope",
    "event_id",
    "agent",
    "session",
    "project",
    "occurred_at",
    "kind",
    "outcome",
    "summary",
    "command",
    "context",
    "references",
    "corrects",
    "correction_reason",
    "coverage",
}


def slug(value):
    return isinstance(value, str) and SLUG.fullmatch(value)


def moment(value):
    if not isinstance(value, str):
        raise ValueError("Agent log timestamp requires an explicit timezone")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Agent log timestamp requires an explicit timezone")
    return parsed


def validate_session(session):
    if (
        not isinstance(session, dict)
        or set(session) != {"id", "agent", "project", "kinds", "expires_at"}
        or not slug(session["id"])
        or session["agent"] not in tuple(AGENTS)
        or (session["project"] is not None and not slug(session["project"]))
        or not isinstance(session["kinds"], list)
        or not 1 <= len(session["kinds"]) <= len(KINDS)
        or any(kind not in tuple(KINDS) for kind in session["kinds"])
        or len(set(session["kinds"])) != len(session["kinds"])
    ):
        raise ValueError("Invalid Agent log session policy")
    moment(session["expires_at"])


def activation(data, now, *, local=True):
    session = data.get("session") if local else None
    if session is None:
        return {"enabled": data["enabled"]}
    return {
        "enabled": now < moment(session["expires_at"]),
        "session_policy": session,
    }


def capture_block_reason(data, fields, now, *, local=True):
    mode = activation(data, now, local=local)
    if not mode["enabled"]:
        return (
            "agent-log-session-expired"
            if "session_policy" in mode
            else "agent-log-disabled-or-memory-paused"
        )
    session = mode.get("session_policy")
    if session is None:
        return None
    if (
        fields["session"] != session["id"]
        or fields["agent"] != session["agent"]
        or fields["project"] != session["project"]
        or fields["kind"] not in session["kinds"]
    ):
        return "agent-log-session-policy"
    allowed_refs = {"content", "journal-event"}
    if fields["kind"] in {"link-found", "page-visited"}:
        allowed_refs.add("url")
    if fields["kind"] == "file-changed":
        allowed_refs.add("file")
    if (
        fields["context"]
        or (fields["command"] is not None and not fields["kind"].startswith("command-"))
        or any(
            ref["kind"] not in allowed_refs
            or (ref["kind"] == "url" and ("?" in ref["target"] or "#" in ref["target"]))
            for ref in fields["references"]
        )
    ):
        return "agent-log-session-needs-redaction"
    return None


def log_text(value, maximum):
    safe_text(value, maximum)
    if re.search(r"https?://[^\s/@:]+:[^\s/@]*@", value, re.IGNORECASE):
        raise ValueError("Credentials in Agent log text rejected")
    for match in re.finditer(
        r"--(?:password|passwd|token|api-key|secret)\s+(\S+)", value, re.IGNORECASE
    ):
        if not match[1].strip("\"'").startswith(("$", "<")):
            raise ValueError("Possible command credential rejected")
    return value


def validate_event(candidate, scope, timezone=None):
    if not isinstance(candidate, dict) or set(candidate) != FIELDS:
        raise ValueError("Agent log requires its documented event fields")
    if type(candidate["schema_version"]) is not int or candidate["schema_version"] != 1:
        raise ValueError("Unsupported Agent log event schema")
    if candidate["scope"] != scope or scope not in {"personal", "work"}:
        raise ValueError("Agent log scope does not match deployment")
    if not slug(candidate["event_id"]) or not slug(candidate["session"]):
        raise ValueError("Agent log IDs must be stable lowercase slugs")
    if candidate["project"] is not None and not slug(candidate["project"]):
        raise ValueError("Agent log project must be a slug or null")
    if not isinstance(candidate["agent"], str) or candidate["agent"] not in AGENTS:
        raise ValueError("Unsupported Agent log agent")
    if not isinstance(candidate["kind"], str) or candidate["kind"] not in KINDS:
        raise ValueError("Unsupported Agent log kind")
    if not isinstance(candidate["outcome"], str) or candidate["outcome"] not in OUTCOMES:
        raise ValueError("Unsupported Agent log outcome")
    if candidate["coverage"] != "reported":
        raise ValueError("This version accepts reported actions, not claimed automatic observation")
    if candidate["kind"] == "command-proposed" and candidate["outcome"] != "unknown":
        raise ValueError("A proposed command has no execution result")
    if candidate["kind"] == "command-attempted" and candidate["outcome"] == "success":
        raise ValueError("A successful execution must be recorded as executed")
    result = dict(candidate)
    for key, limit in [("summary", 600), ("context", 1000), ("correction_reason", 400)]:
        result[key] = log_text(candidate[key], limit).strip()
    if not result["summary"]:
        raise ValueError("Agent log summary required")
    if candidate["command"] is not None:
        log_text(candidate["command"], 4000)
        if not candidate["command"].strip() or candidate["kind"] not in KINDS & {
            "command-proposed",
            "command-attempted",
            "command-executed",
            "check",
        }:
            raise ValueError("Command text requires a command or check event")
    elif candidate["kind"].startswith("command-"):
        raise ValueError("Command text required")
    if candidate["occurred_at"] is not None:
        at = moment(candidate["occurred_at"])
        result["occurred_at"] = (at.astimezone(ZoneInfo(timezone)) if timezone else at).isoformat()
    if candidate["corrects"] is not None:
        if not slug(candidate["corrects"]) or candidate["corrects"] == candidate["event_id"]:
            raise ValueError("Invalid Agent log correction target")
        if not result["correction_reason"]:
            raise ValueError("A correction requires its reason")
    elif result["correction_reason"]:
        raise ValueError("A correction reason requires a target")
    refs = candidate["references"]
    if not isinstance(refs, list) or len(refs) > 6:
        raise ValueError("Agent log accepts at most six references")
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"kind", "target", "label"}:
            raise ValueError("Invalid Agent log reference")
        if not isinstance(ref["kind"], str):
            raise ValueError("Invalid Agent log reference kind")
        target = log_text(ref["target"], 2000)
        if not log_text(ref["label"], 160).strip() or any(c in target for c in "\r\n\t"):
            raise ValueError("Invalid Agent log reference text")
        if ref["kind"] in {"url", "content"}:
            validate_link(dict(target=target, label=ref["label"], annotation_id=None))
            external = target.startswith(("https://", "http://"))
            if external != (ref["kind"] == "url"):
                raise ValueError("Reference kind does not match its target")
            if (
                not external
                and target.split(":", 2)[0] != "documentation"
                and target.split(":", 2)[1] != scope
            ):
                raise ValueError("Cross-profile Agent log reference rejected")
        elif ref["kind"] == "journal-event":
            if not slug(target):
                raise ValueError("Journal reference requires an event ID")
        elif ref["kind"] == "file":
            if not target.strip() or len(target) > 500 or "://" in target:
                raise ValueError("File reference must be bounded inert text")
        else:
            raise ValueError("Unsupported Agent log reference kind")
        identity = (ref["kind"], target)
        if identity in seen:
            raise ValueError("Duplicate Agent log reference")
        seen.add(identity)
    if candidate["kind"] in {"link-found", "page-visited"} and not any(
        r["kind"] == "url" for r in refs
    ):
        raise ValueError("Link and visit events require an HTTP(S) reference")
    if candidate["kind"] == "file-changed" and not any(r["kind"] == "file" for r in refs):
        raise ValueError("File changes require an inert file reference")
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 12000:
        raise ValueError("Agent log event exceeds its byte limit")
    return result


def decode(raw):
    try:
        return _decode(raw)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("Agent log store is invalid or exceeds its limits") from None


def _decode(raw):
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Agent log store exceeds size limit")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or type(data["schema_version"]) is not int
        or data["schema_version"] not in {1, 2}
        or set(data)
        != {"schema_version", "scope", "enabled", "revision", "items"}
        | ({"session"} if data["schema_version"] == 2 else set())
        or not isinstance(data["scope"], str)
        or data["scope"] not in {"personal", "work"}
        or type(data["enabled"]) is not bool
        or type(data["revision"]) is not int
        or not 0 <= data["revision"] <= 1_000_000_000
        or not isinstance(data["items"], list)
        or len(data["items"]) > MAX_EVENTS
    ):
        raise ValueError("Unsupported Agent log store")
    if data["schema_version"] == 2:
        if data["enabled"]:
            raise ValueError("Session and profile-wide Agent log activation are exclusive")
        validate_session(data["session"])
    seen, corrected = {}, set()
    for item in data["items"]:
        if not isinstance(item, dict) or set(item) != FIELDS | {"recorded_at"}:
            raise ValueError("Invalid Agent log record")
        payload = {key: item[key] for key in FIELDS}
        if validate_event(payload, data["scope"]) != payload or item["event_id"] in seen:
            raise ValueError("Invalid or duplicate Agent log event")
        moment(item["recorded_at"])
        target = item["corrects"]
        if target:
            original = seen.get(target)
            if not original or original["project"] != item["project"] or target in corrected:
                raise ValueError("Invalid Agent log correction history")
            corrected.add(target)
        seen[item["event_id"]] = item
    return data


class AgentLog:
    def __init__(self, brain):
        self.brain = brain
        self.lock = FileLock(scoped_path(brain.state, "agent-log.lock"), timeout=5)

    def _read(self):
        self.brain.ledger()
        path = scoped_path(self.brain.state, "agent-log.json")
        if not path.exists():
            return dict(
                schema_version=1, scope=self.brain.scope, enabled=False, revision=0, items=[]
            )
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Agent log store exceeds size limit")
        data = decode(raw.decode("utf-8"))
        if data["scope"] != self.brain.scope:
            raise ValueError("Agent log scope does not match deployment")
        return data

    def export(self):
        with self.lock:
            return self._read()

    def status(self, *, local=True):
        data = self.export()
        return dict(
            activation(data, self.brain.now(), local=local),
            scope=data["scope"],
            revision=data["revision"],
            total=len(data["items"]),
            coverage="reported",
        )

    @staticmethod
    def _serialize(data):
        raw = json.dumps(
            dict(data, revision=data["revision"] + 1), ensure_ascii=False, separators=(",", ":")
        )
        decode(raw)
        return raw

    def _write(self, data):
        atomic_write(scoped_path(self.brain.state, "agent-log.json"), self._serialize(data))
        data["revision"] += 1

    def configure(self, enabled, revision):
        if type(enabled) is not bool or type(revision) is not int:
            raise ValueError("Agent log configuration requires enabled and current revision")
        with self.brain.lock, self.lock:
            data = self._read()
            if data["revision"] != revision:
                raise Conflict("Agent log changed; refresh before changing activation")
            if "session" in data:
                if enabled:
                    raise Conflict("Close the Agent log session before enabling the whole profile")
                data.pop("session")
                data["schema_version"] = 1
                self._write(data)
                return dict(enabled=False, revision=data["revision"])
            if data["enabled"] != enabled:
                if enabled and scoped_path(self.brain.state, PENDING_CHECKPOINT).exists():
                    raise Conflict("Retry the pending checkpoint before enabling Agent log")
                data["enabled"] = enabled
                self._write(data)
            return dict(enabled=data["enabled"], revision=data["revision"])

    def start_session(self, session_id, agent, project, kinds, minutes, *, apply=False):
        if type(minutes) is not int or not 1 <= minutes <= 480:
            raise ValueError("Agent log session duration must be 1–480 minutes")
        with self.brain.lock, self.lock:
            data = self._read()
            now = self.brain.now().astimezone(timezone.utc)
            session = dict(
                id=session_id,
                agent=agent,
                project=project,
                kinds=kinds,
                expires_at=(now + timedelta(minutes=minutes)).isoformat(),
            )
            validate_session(session)
            if "session" in data or data["enabled"]:
                raise Conflict("Disable Agent log before opening a new session")
            if scoped_path(self.brain.state, "paused").exists():
                raise Conflict("Resume memory before opening an Agent log session")
            if scoped_path(self.brain.state, PENDING_CHECKPOINT).exists():
                raise Conflict("Retry the pending checkpoint before opening an Agent log session")
            if apply:
                data.update(schema_version=2, session=session)
                self._write(data)
            return dict(
                status="enabled" if apply else "preview",
                scope=data["scope"],
                revision=data["revision"],
                session_policy=session,
            )

    def record(self, candidate, *, checkpoint_at=None, local=True):
        fields = validate_event(candidate, self.brain.scope, self.brain.config["timezone"])
        with self.brain.lock, self.lock:
            data = self._read()
            old = next(
                (row for row in data["items"] if row["event_id"] == fields["event_id"]), None
            )
            if old:
                if any(old[key] != fields[key] for key in FIELDS):
                    raise Conflict("Agent log event ID already has different content")
                return dict(status="duplicate", event_id=fields["event_id"])
            if checkpoint_at is None and scoped_path(self.brain.state, PENDING_CHECKPOINT).exists():
                return dict(status="blocked", reason="pending-checkpoint")
            if (self.brain.state / "paused").exists():
                return dict(status="blocked", reason="agent-log-disabled-or-memory-paused")
            now = self.brain.now()
            if reason := capture_block_reason(
                data, fields, moment(checkpoint_at) if checkpoint_at else now, local=local
            ):
                return dict(status="blocked", reason=reason)
            data["items"].append({**fields, "recorded_at": checkpoint_at or now.isoformat()})
            self._write(data)
            return dict(status="saved", event_id=fields["event_id"])

    def read(self, event_id):
        if not slug(event_id):
            raise ValueError("Exact Agent log event ID required")
        data = self.export()
        item = next((row for row in data["items"] if row["event_id"] == event_id), None)
        if item is None:
            raise ValueError("Agent log event does not exist")
        corrected_by = next(
            (r["event_id"] for r in data["items"] if r["corrects"] == event_id), None
        )
        return dict(scope=data["scope"], item=item, corrected_by=corrected_by)

    def query(self, query="", filters=None, offset=0, max_chars=8000, *, local=True):
        safe_text(query, 300)
        filters = {} if filters is None else filters
        allowed = {
            "start_date",
            "end_date",
            "project",
            "session",
            "agent",
            "kind",
            "outcome",
            "journal_event",
        }
        if not isinstance(filters, dict) or set(filters) - allowed:
            raise ValueError("Unsupported Agent log filters")
        if (
            type(offset) is not int
            or offset < 0
            or type(max_chars) is not int
            or not 4000 <= max_chars <= 20000
        ):
            raise ValueError("Use nonnegative offset and 4000–20000 character budget")
        for key in {"project", "session", "journal_event"} & filters.keys():
            if not slug(filters[key]):
                raise ValueError("Agent log filters require exact slugs")
        for key, choices in [("agent", AGENTS), ("kind", KINDS), ("outcome", OUTCOMES)]:
            if key in filters and (
                not isinstance(filters[key], str) or filters[key] not in choices
            ):
                raise ValueError("Unsupported Agent log filter value")
        now = self.brain.now()
        today = now.date()
        try:
            end = date.fromisoformat(filters.get("end_date", today.isoformat()))
            start = date.fromisoformat(
                filters.get(
                    "start_date", (end - timedelta(days=min(6, end.toordinal() - 1))).isoformat()
                )
            )
            if (
                any(
                    str(value) != filters[key]
                    for key, value in [("start_date", start), ("end_date", end)]
                    if key in filters
                )
                or not 0 <= (end - start).days <= 30
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Agent log dates require a 1–31 day YYYY-MM-DD window") from None
        data = self.export()
        zone = ZoneInfo(self.brain.config["timezone"])
        terms = query.casefold().split()
        selected = []
        corrected = {row["corrects"]: row["event_id"] for row in data["items"] if row["corrects"]}
        for index, row in enumerate(data["items"]):
            at = moment(row["occurred_at"] or row["recorded_at"]).astimezone(zone)
            if not start <= at.date() <= end:
                continue
            if any(
                row[key] != filters[key]
                for key in {"project", "session", "agent", "kind", "outcome"} & filters.keys()
            ):
                continue
            if "journal_event" in filters and not any(
                r["kind"] == "journal-event" and r["target"] == filters["journal_event"]
                for r in row["references"]
            ):
                continue
            haystack = " ".join(
                [
                    row["summary"],
                    row["command"] or "",
                    row["context"],
                    *[r["target"] + " " + r["label"] for r in row["references"]],
                ]
            ).casefold()
            if all(term in haystack for term in terms):
                selected.append((at, index, row))
        selected.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        result = dict(
            activation(data, now, local=local),
            scope=data["scope"],
            revision=data["revision"],
            today=str(today),
            timezone=str(zone),
            start_date=str(start),
            end_date=str(end),
            total=len(selected),
            items=[],
            next_offset=None,
            truncated=False,
            coverage="reported",
        )
        for index in range(offset, min(offset + 20, len(selected))):
            at, _, row = selected[index]
            item = {
                key: row[key]
                for key in [
                    "event_id",
                    "agent",
                    "session",
                    "project",
                    "kind",
                    "outcome",
                    "occurred_at",
                    "recorded_at",
                    "coverage",
                    "corrects",
                ]
            }
            item.update(
                day=str(at.date()),
                summary=row["summary"][:200],
                command_preview=(row["command"] or "")[:300],
                reference_count=len(row["references"]),
                corrected_by=corrected.get(row["event_id"]),
                preview_truncated=len(row["summary"]) > 200 or len(row["command"] or "") > 300,
            )
            item["reference_preview"] = (
                row["references"][0]["target"][:300] if row["references"] else ""
            )
            if terms:
                from second_brain.catalog import search_excerpt

                text = " ".join(
                    [
                        row["summary"],
                        row["command"] or "",
                        row["context"],
                        *[r["target"] + " " + r["label"] for r in row["references"]],
                    ]
                )
                item["match_context"] = search_excerpt(text, query, 220)
            result["items"].append(item)
            result["next_offset"] = index + 1 if index + 1 < len(selected) else None
            if len(json.dumps(result, ensure_ascii=False)) > max_chars:
                result["items"].pop()
                result["next_offset"] = index
                result["truncated"] = True
                if not result["items"]:
                    raise ValueError("Agent log metadata exceeds budget; increase max_chars")
                break
        return result
