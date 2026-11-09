"""Local issue context, independent of verified notes and tracked journal tasks."""

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from filelock import FileLock

from second_brain.annotations import Annotations, Conflict
from second_brain.catalog import Catalog
from second_brain.core import SLUG, atomic_write, note_metadata, safe_text, scoped_path

KEY = re.compile(r"[A-Z][A-Z0-9]{0,19}-[0-9]{1,10}\Z")
STATES = {"open", "in-progress", "blocked", "done"}
MAX_BYTES = 8_000_000
MAX_EVENTS = 10_000
FIELDS = {"key", "title", "body", "status", "project", "tags", "links"}
EDITABLE = FIELDS - {"key"}


class TaskNotFound(ValueError):
    pass


def task_key(value):
    key = safe_text(value, 40).strip().upper()
    if not KEY.fullmatch(key):
        raise ValueError("Use an issue code such as DEMO-1234")
    return key


def validate_link(link):
    if not isinstance(link, dict) or set(link) != {"target", "annotation_id", "label"}:
        raise ValueError("Invalid task link")
    target = safe_text(link["target"], 2000)
    if not safe_text(link["label"], 160).strip():
        raise ValueError("Link label required")
    if link["annotation_id"] is not None and (
        not isinstance(link["annotation_id"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", link["annotation_id"])
    ):
        raise ValueError("Invalid fragment ID")
    url = urlsplit(target)
    if url.scheme in {"http", "https"}:
        if (
            not url.hostname
            or url.username is not None
            or url.password is not None
            or any(c.isspace() or ord(c) < 32 for c in target)
            or "\\" in target
            or link["annotation_id"] is not None
            or any(
                name.casefold().replace("-", "_")
                in {
                    "token",
                    "access_token",
                    "api_key",
                    "secret",
                    "password",
                    "auth",
                    "authorization",
                    "key",
                    "code",
                    "sig",
                    "signature",
                    "client_secret",
                    "credential",
                    "x_amz_credential",
                    "x_amz_signature",
                    "x_goog_signature",
                }
                or name.casefold().replace("-", "_").endswith(("_token", "_secret", "_password"))
                for name, _ in parse_qsl(url.query, keep_blank_values=True)
                + parse_qsl(url.fragment, keep_blank_values=True)
            )
        ):
            raise ValueError("Use an HTTP(S) reference without credentials")
        url.port  # Validate malformed ports without contacting the destination.
    else:
        parts = target.split(":", 2)
        if (
            len(parts) != 3
            or parts[0] not in {"documentation", "note", "journal", "task"}
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", parts[1])
            or not parts[2]
            or "\\" in parts[2]
            or any(part in {"", ".", ".."} for part in parts[2].split("/"))
        ):
            raise ValueError("Use an authorized content ID or HTTP(S) URL")


def validate_fields(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Invalid task fields")
    key = task_key(value["key"])
    title = safe_text(value["title"], 160).strip()
    if not title or not isinstance(value["status"], str) or value["status"] not in STATES:
        raise ValueError("Task title and supported state required")
    body = safe_text(value["body"], 12000)
    metadata = note_metadata({"tags": value["tags"], "project": value["project"]})
    links = value["links"]
    if not isinstance(links, list) or len(links) > 40:
        raise ValueError("At most forty links per task")
    seen = set()
    for link in links:
        validate_link(link)
        target = link["target"]
        identity = (target, link["annotation_id"])
        if identity in seen:
            raise ValueError("Duplicate task link")
        seen.add(identity)
    return dict(
        key=key,
        title=title,
        body=body,
        status=value["status"],
        project=metadata["project"],
        tags=metadata["tags"],
        links=links,
    )


def decode(raw):
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Task store exceeds size limit")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] not in {1, 2}
        or set(data)
        != (
            {"schema_version", "scope", "items"}
            | ({"events"} if data["schema_version"] == 2 else set())
        )
        or data["scope"] not in {"personal", "work"}
        or not isinstance(data["items"], list)
        or len(data["items"]) > 1000
    ):
        raise ValueError("Unsupported task store")
    versions = {}
    for item in data["items"]:
        if not isinstance(item, dict) or set(item) != FIELDS | {
            "version",
            "created_at",
            "updated_at",
        }:
            raise ValueError("Invalid task record")
        if validate_fields({key: item[key] for key in FIELDS}) != {
            key: item[key] for key in FIELDS
        }:
            raise ValueError("Noncanonical task metadata")
        if type(item["version"]) is not int or not 1 <= item["version"] <= 1_000_000:
            raise ValueError("Invalid task version")
        for field in ["created_at", "updated_at"]:
            if datetime.fromisoformat(item[field]).tzinfo is None:
                raise ValueError("Task dates require timezone")
        if item["key"] in versions:
            raise ValueError("Duplicate task code")
        versions[item["key"]] = item["version"]
    events = data.get("events", {})
    if not isinstance(events, dict) or len(events) > MAX_EVENTS:
        raise ValueError("Invalid task events")
    for event_id, event in events.items():
        if (
            not SLUG.fullmatch(event_id)
            or not isinstance(event, dict)
            or set(event) != {"fingerprint", "key", "version"}
            or not isinstance(event["fingerprint"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", event["fingerprint"])
            or not isinstance(event["key"], str)
            or type(event["version"]) is not int
            or not 1 <= event["version"] <= versions.get(event["key"], 0)
        ):
            raise ValueError("Invalid task event")
    return data


class TaskPages:
    def __init__(self, brain):
        self.brain = brain
        self.lock = FileLock(scoped_path(brain.state, "task-pages.lock"), timeout=5)

    def _read(self):
        self.brain.ledger()  # Recheck deployment identity before every read/write.
        path = scoped_path(self.brain.state, "task-pages.json")
        if not path.exists():
            return {"schema_version": 1, "scope": self.brain.scope, "items": []}
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Task store exceeds size limit")
        data = decode(path.read_text(encoding="utf-8"))
        if data["scope"] != self.brain.scope:
            raise ValueError("Task scope does not match deployment")
        return data

    def export(self):
        with self.lock:
            return self._read()

    def read(self, key):
        key = task_key(key)
        item = next((row for row in self.export()["items"] if row["key"] == key), None)
        if item is None:
            raise TaskNotFound("Task does not exist")
        return item

    def save(self, payload):
        if not isinstance(payload, dict) or set(payload) != FIELDS | {"version"}:
            raise ValueError("Task requires all fields and current version")
        fields = validate_fields({key: payload[key] for key in FIELDS})
        if type(payload["version"]) is not int or not 0 <= payload["version"] < 1_000_000:
            raise ValueError("Invalid task version")
        marks = Annotations(self.brain)
        with marks.lock, self.lock:
            data = self._read()
            old = next((row for row in data["items"] if row["key"] == fields["key"]), None)
            if old and all(old[key] == fields[key] for key in FIELDS):
                return old
            if payload["version"] != (old["version"] if old else 0):
                raise Conflict("Task changed; refresh before saving")
            item = self._update(data, fields, old, marks)
            self._write(data)
            return item

    def edit(self, key, expected_version, changes, event_id):
        key = task_key(key)
        if type(expected_version) is not int or not 0 <= expected_version <= 1_000_000:
            raise ValueError("Invalid task version")
        if not SLUG.fullmatch(safe_text(event_id, 100)):
            raise ValueError("Use a stable event ID of lowercase letters, digits and hyphens")
        if not isinstance(changes, dict) or not changes or set(changes) - EDITABLE:
            raise ValueError("Provide one or more editable task fields")
        fingerprint = hashlib.sha256(
            json.dumps([key, expected_version, changes], sort_keys=True).encode()
        ).hexdigest()
        result = {"key": key, "event_id": event_id}
        marks = Annotations(self.brain)
        with self.brain.lock, marks.lock, self.lock:
            data = self._read()
            events = data.get("events", {})
            previous = events.get(event_id)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    return dict(result, status="conflict", reason="event-id-reused")
                return dict(result, status="duplicate", version=previous["version"])
            if scoped_path(self.brain.state, "paused").exists():
                return dict(result, status="blocked", reason="paused")
            old = next((row for row in data["items"] if row["key"] == key), None)
            version = old["version"] if old else 0
            if expected_version != version:
                return dict(result, status="conflict", reason="version-mismatch", version=version)
            if len(events) >= MAX_EVENTS:
                return dict(result, status="blocked", reason="task-event-limit")
            base = (
                {field: old[field] for field in EDITABLE}
                if old
                else dict(title="", body="", status="open", project=None, tags=[], links=[])
            )
            fields = validate_fields({**base, **changes, "key": key})
            unchanged = old and all(old[field] == fields[field] for field in FIELDS)
            item = old if unchanged else self._update(data, fields, old, marks)
            events[event_id] = dict(fingerprint=fingerprint, key=key, version=item["version"])
            self._write(dict(data, schema_version=2, events=events))
            return dict(
                result, status="unchanged" if unchanged else "saved", version=item["version"]
            )

    def _update(self, data, fields, old, marks):
        self._validate_new_links(data["items"], fields["links"], old["links"] if old else [], marks)
        now = self.brain.now().isoformat()
        item = {
            **fields,
            "version": old["version"] + 1 if old else 1,
            "created_at": old["created_at"] if old else now,
            "updated_at": now,
        }
        data["items"] = [row for row in data["items"] if row["key"] != item["key"]] + [item]
        return item

    def _validate_new_links(self, records, links, old_links, marks):
        new_links = [link for link in links if link not in old_links]
        sources = {}
        fragments = None
        for link in new_links:
            target = link["target"]
            if urlsplit(target).scheme in {"http", "https"}:
                continue
            kind, source, _ = target.split(":", 2)
            if (kind, source) not in sources:
                # Reuse the locked task records instead of acquiring the task lock again.
                if kind == "task":
                    rows = self.rows(records) if source == self.brain.scope else []
                else:
                    rows = Catalog(self.brain).snapshot(kind, source)["items"]
                sources[kind, source] = {row["id"] for row in rows}
            if target not in sources[kind, source]:
                raise ValueError("Link destination is not available")
            if link["annotation_id"]:
                if fragments is None:
                    fragments = {
                        (mark["id"], mark["document_id"]) for mark in marks.export()["items"]
                    }
                if (link["annotation_id"], target) not in fragments:
                    raise ValueError("Fragment is not available")

    def _write(self, data):
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        decode(raw)
        atomic_write(scoped_path(self.brain.state, "task-pages.json"), raw)

    def list(self, filters=None, offset=0):
        filters = {} if filters is None else filters
        if not isinstance(filters, dict) or set(filters) - {"project", "tags", "status"}:
            raise ValueError("Unsupported task filters")
        if "status" in filters and filters["status"] not in tuple(STATES):
            raise ValueError("Invalid task status filter")
        if type(offset) is not int or not 0 <= offset <= 1000:
            raise ValueError("Invalid task offset")
        metadata = note_metadata(filters)
        tags = set(metadata["tags"])
        items = [
            {key: value for key, value in item.items() if key not in {"body", "links"}}
            for item in self.export()["items"]
            if ("project" not in filters or item["project"] == metadata["project"])
            and ("status" not in filters or item["status"] == filters["status"])
            and ("tags" not in filters or (tags <= set(item["tags"]) if tags else not item["tags"]))
        ]
        items.sort(key=lambda item: item["key"])
        end = offset + 20
        return dict(
            scope=self.brain.scope,
            items=items[offset:end],
            total=len(items),
            next_offset=end if end < len(items) else None,
        )

    def rows(self, records=None):
        records = self.export()["items"] if records is None else records
        return [
            dict(
                id=f"task:{self.brain.scope}:{item['key']}",
                kind="task",
                source=self.brain.scope,
                path=item["key"],
                title=item["key"] + " · " + item["title"],
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                metadata=dict(tags=item["tags"], project=item["project"], status=item["status"]),
            )
            for item in records
        ]

    @staticmethod
    def markdown(item):
        return f"# {item['key']} · {item['title']}\n\n" + item["body"]

    def content(self, key):
        return self.markdown(self.read(key))
