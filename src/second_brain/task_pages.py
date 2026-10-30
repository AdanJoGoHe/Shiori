"""Local issue context, independent of verified notes and tracked journal tasks."""

import json
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from filelock import FileLock

from second_brain.annotations import Conflict
from second_brain.core import atomic_write, note_metadata, safe_text, scoped_path

KEY = re.compile(r"[A-Z][A-Z0-9]{0,19}-[0-9]{1,10}\Z")
STATES = {"open", "in-progress", "blocked", "done"}
MAX_BYTES = 8_000_000
FIELDS = {"key", "title", "body", "status", "project", "tags", "links"}


def task_key(value):
    key = safe_text(value, 40).strip().upper()
    if not KEY.fullmatch(key):
        raise ValueError("Use an issue code such as DEMO-1234")
    return key


def validate_fields(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Invalid task fields")
    key = task_key(value["key"])
    title = safe_text(value["title"], 160).strip()
    if not title or value["status"] not in STATES:
        raise ValueError("Task title and supported state required")
    body = safe_text(value["body"], 12000)
    metadata = note_metadata({"tags": value["tags"], "project": value["project"]})
    links = value["links"]
    if not isinstance(links, list) or len(links) > 40:
        raise ValueError("At most forty links per task")
    seen = set()
    for link in links:
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
                    name.casefold() in {"token", "access_token", "api_key", "secret", "password"}
                    for name, _ in parse_qsl(url.query)
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
        or set(data) != {"schema_version", "scope", "items"}
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or data["scope"] not in {"personal", "work"}
        or not isinstance(data["items"], list)
        or len(data["items"]) > 1000
    ):
        raise ValueError("Unsupported task store")
    keys = set()
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
        if item["key"] in keys:
            raise ValueError("Duplicate task code")
        keys.add(item["key"])
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
            raise ValueError("Task does not exist")
        return item

    def save(self, payload):
        if not isinstance(payload, dict) or set(payload) != FIELDS | {"version"}:
            raise ValueError("Task requires all fields and current version")
        fields = validate_fields({key: payload[key] for key in FIELDS})
        if type(payload["version"]) is not int or not 0 <= payload["version"] < 1_000_000:
            raise ValueError("Invalid task version")
        with self.lock:
            data = self._read()
            old = next((row for row in data["items"] if row["key"] == fields["key"]), None)
            if old and all(old[key] == fields[key] for key in FIELDS):
                return old
            if payload["version"] != (old["version"] if old else 0):
                raise Conflict("Task changed; refresh before saving")
            now = self.brain.now().isoformat()
            item = {
                **fields,
                "version": payload["version"] + 1,
                "created_at": old["created_at"] if old else now,
                "updated_at": now,
            }
            data["items"] = [row for row in data["items"] if row["key"] != item["key"]] + [item]
            raw = json.dumps(data, ensure_ascii=False, indent=2)
            decode(raw)
            atomic_write(scoped_path(self.brain.state, "task-pages.json"), raw)
            return item

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
