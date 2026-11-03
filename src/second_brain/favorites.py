"""Deployment-local preferences; a favorite is never evidence or a downloaded page."""

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

from filelock import FileLock

from second_brain.annotations import Conflict
from second_brain.catalog import Catalog, markdown_body
from second_brain.core import atomic_write, note_metadata, safe_text, scoped_path
from second_brain.task_pages import validate_link

MAX_BYTES = 8_000_000
MAX_ITEMS = 1000
FIELDS = {"target", "title", "project", "tags"}
KINDS = {"documentation", "note", "journal", "task", "web"}


def is_web(target):
    return urlsplit(target).scheme in {"http", "https"}


def favorite_id(target):
    return hashlib.sha256(target.encode("utf-8")).hexdigest()[:32]


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid favorite ID")
    return value


def fields(value, scope):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Favorite requires target, title, project and tags")
    title = safe_text(value["title"], 160).strip()
    validate_link(dict(target=value["target"], label=title, annotation_id=None))
    target = value["target"]
    if not is_web(target):
        kind, source, _ = target.split(":", 2)
        if kind != "documentation" and source != scope:
            raise ValueError("Favorite target belongs to another scope")
    metadata = note_metadata(dict(project=value["project"], tags=value["tags"]))
    return dict(target=target, title=title, project=metadata["project"], tags=metadata["tags"])


def decode(raw):
    try:
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise ValueError
        data = json.loads(raw)
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "scope", "items"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["scope"] not in {"personal", "work"}
            or not isinstance(data["items"], list)
            or len(data["items"]) > MAX_ITEMS
        ):
            raise ValueError
        seen = set()
        for row in data["items"]:
            if not isinstance(row, dict) or set(row) != FIELDS | {
                "id",
                "version",
                "created_at",
                "updated_at",
                "deleted",
            }:
                raise ValueError
            content = {key: row[key] for key in FIELDS}
            if fields(content, data["scope"]) != content:
                raise ValueError
            if row["id"] != favorite_id(row["target"]) or row["id"] in seen:
                raise ValueError
            seen.add(row["id"])
            if type(row["version"]) is not int or not 1 <= row["version"] <= 1_000_000:
                raise ValueError
            if type(row["deleted"]) is not bool:
                raise ValueError
            for key in ("created_at", "updated_at"):
                if datetime.fromisoformat(row[key]).tzinfo is None:
                    raise ValueError
            if datetime.fromisoformat(row["updated_at"]) < datetime.fromisoformat(
                row["created_at"]
            ):
                raise ValueError
        return data
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise ValueError("Invalid or unsupported favorites store") from None


class Favorites:
    def __init__(self, brain):
        self.brain = brain
        self.lock = FileLock(scoped_path(brain.state, "favorites.lock"), timeout=5)

    def _read(self):
        self.brain.ledger()
        path = scoped_path(self.brain.state, "favorites.json")
        if not path.exists():
            return dict(schema_version=1, scope=self.brain.scope, items=[])
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Favorites store exceeds size limit")
        data = decode(path.read_text(encoding="utf-8"))
        if data["scope"] != self.brain.scope:
            raise ValueError("Favorites scope does not match deployment")
        return data

    def export(self):
        with self.lock:
            return self._read()

    def _write(self, data):
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        decode(raw)
        atomic_write(scoped_path(self.brain.state, "favorites.json"), raw)

    def prepare(self, payload):
        if not isinstance(payload, dict) or set(payload) != FIELDS | {"version"}:
            raise ValueError("Favorite requires all fields and current version")
        content = fields({key: payload[key] for key in FIELDS}, self.brain.scope)
        version = payload["version"]
        if type(version) is not int or not 0 <= version < 1_000_000:
            raise ValueError("Invalid favorite version")
        target = content["target"]
        # Validate new/edited internal destinations through the same authorized reader.
        if not is_web(target):
            Catalog(self.brain).read(target)
        return content, version

    def save(self, payload):
        content, version = self.prepare(payload)
        target = content["target"]
        with self.lock:
            data = self._read()
            identity = favorite_id(target)
            old = next((r for r in data["items"] if r["id"] == identity), None)
            if old and not old["deleted"] and all(old[k] == content[k] for k in FIELDS):
                return old
            expected = old["version"] if old else 0
            if version != expected:
                raise Conflict("Favorite changed; refresh before saving")
            now = self.brain.now().isoformat()
            item = dict(
                **content,
                id=identity,
                version=expected + 1,
                deleted=False,
                created_at=old["created_at"] if old else now,
                updated_at=now,
            )
            data["items"] = [r for r in data["items"] if r["id"] != identity] + [item]
            self._write(data)
            return item

    def remove(self, identity, version):
        valid_id(identity)
        if type(version) is not int or not 1 <= version < 1_000_000:
            raise ValueError("Current favorite version required")
        with self.lock:
            data = self._read()
            row = next((r for r in data["items"] if r["id"] == identity), None)
            if row and not row["deleted"]:
                if row["version"] != version:
                    raise Conflict("Favorite changed; refresh before removing")
                row.update(
                    deleted=True, version=version + 1, updated_at=self.brain.now().isoformat()
                )
                self._write(data)
            return dict(id=identity, removed=True, version=row["version"] if row else version)

    def query(
        self, query="", filters=None, offset=0, max_chars=8000, identity=None, order="recent"
    ):
        safe_text(query, 300)
        filters = {} if filters is None else filters
        if not isinstance(filters, dict) or set(filters) - {"project", "tags", "kind", "target"}:
            raise ValueError("Unsupported favorites filters")
        metadata = note_metadata({k: filters[k] for k in ("project", "tags") if k in filters})
        filters = {k: metadata[k] if k in {"project", "tags"} else v for k, v in filters.items()}
        if "kind" in filters and (
            not isinstance(filters["kind"], str) or filters["kind"] not in KINDS
        ):
            raise ValueError("Unsupported favorite kind")
        if "target" in filters:
            safe_text(filters["target"], 2000)
        if identity is not None:
            valid_id(identity)
        if (
            type(offset) is not int
            or offset < 0
            or type(max_chars) is not int
            or not 4000 <= max_chars <= 20000
            or order not in {"recent", "title"}
        ):
            raise ValueError("Use nonnegative offset, 4000–20000 budget and recent/title order")
        data = self.export()
        catalog = Catalog(self.brain)
        snapshot = catalog.snapshot()
        authorized = {r["id"]: r for r in snapshot["items"]}
        terms = query.casefold().split()
        selected = []
        for row in data["items"]:
            if row["deleted"] or (identity is not None and row["id"] != identity):
                continue
            kind = "web" if is_web(row["target"]) else row["target"].split(":", 1)[0]
            if any(row[k] != filters[k] for k in ("project", "target") if k in filters):
                continue
            if "kind" in filters and kind != filters["kind"]:
                continue
            if "tags" in filters and not (
                set(filters["tags"]) <= set(row["tags"]) if filters["tags"] else not row["tags"]
            ):
                continue
            item = {k: v for k, v in row.items() if k != "deleted"}
            item.update(
                kind=kind,
                source="web" if kind == "web" else row["target"].split(":", 2)[1],
                available=kind == "web",
                excerpt="",
                content_id=None,
            )
            text = ""
            if row["target"] in authorized:
                try:
                    _, text = catalog.read(row["target"], snapshot)
                    text = markdown_body(text).strip()
                    heading = "# " + authorized[row["target"]]["title"] + "\n"
                    if text.startswith(heading):
                        text = text[len(heading) :].lstrip()
                    item.update(available=True, content_id=row["target"])
                except (ValueError, OSError):
                    pass
            haystack = " ".join([row["title"], row["target"], *row["tags"], text]).casefold()
            if not all(term in haystack for term in terms):
                continue
            if text:
                start = max(0, text.casefold().find(terms[0]) - 70) if terms else 0
                item["excerpt"] = text[start : start + 300]
            selected.append(item)
        selected.sort(
            key=(lambda r: (r["title"].casefold(), r["id"]))
            if order == "title"
            else (lambda r: (datetime.fromisoformat(r["updated_at"]), r["id"])),
            reverse=order == "recent",
        )
        result = dict(
            scope=self.brain.scope,
            total=len(selected),
            items=[],
            next_offset=None,
            truncated=False,
            errors=snapshot["errors"][:5],
            error_count=len(snapshot["errors"]),
            diagnostics_truncated=len(snapshot["errors"]) > 5,
            catalog_truncated=snapshot["truncated"],
            preference_only=True,
            removed_version=next(
                (
                    r["version"]
                    for r in data["items"]
                    if r["deleted"] and r["target"] == filters.get("target")
                ),
                None,
            ),
        )
        for index in range(offset, min(offset + 20, len(selected))):
            result["items"].append(selected[index])
            result["next_offset"] = index + 1 if index + 1 < len(selected) else None
            if len(json.dumps(result, ensure_ascii=False)) > max_chars:
                result["items"].pop()
                result.update(next_offset=index, truncated=True)
                if not result["items"]:
                    raise ValueError("Favorite metadata exceeds budget; increase max_chars")
                break
        return result
