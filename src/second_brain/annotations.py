"""Bounded local sidecar; source documents and the memory ledger are never written."""

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime
from html.parser import HTMLParser

from filelock import FileLock

from second_brain.core import SLUG, atomic_write, safe_text, scoped_path

COLORS = {"yellow", "green", "blue", "pink", "orange", "violet"}
MAX_BYTES = 8_000_000
MAX_ITEMS = 1000
MAX_CATEGORIES = 100


def category_name(label):
    label = " ".join(unicodedata.normalize("NFKC", safe_text(label, 100)).split())
    if not label:
        raise ValueError("Category requires a name")
    return label


def name_key(label):
    return "".join(
        c for c in unicodedata.normalize("NFKD", label.casefold()) if not unicodedata.combining(c)
    )


def default_categories():
    return [
        {"id": key, "label": label, "color": color, "archived": False, "version": 1}
        for key, label, color in [
            ("comando", "Comando", "green"),
            ("informacion-importante", "Información importante", "yellow"),
            ("direccion-ip", "Dirección IP", "blue"),
            ("url", "URL", "violet"),
            ("ruta", "Ruta", "orange"),
        ]
    ]


def validate_categories(categories):
    if not isinstance(categories, list) or len(categories) > MAX_CATEGORIES:
        raise ValueError("Too many categories")
    ids, names = set(), set()
    for row in categories:
        if not isinstance(row, dict) or set(row) != {"id", "label", "color", "archived", "version"}:
            raise ValueError("Invalid category fields")
        if not isinstance(row["id"], str) or not SLUG.fullmatch(row["id"]):
            raise ValueError("Invalid category ID")
        if category_name(row["label"]) != row["label"]:
            raise ValueError("Category name is not normalized")
        if not isinstance(row["color"], str) or row["color"] not in COLORS:
            raise ValueError("Invalid category color")
        if (
            type(row["archived"]) is not bool
            or type(row["version"]) is not int
            or row["version"] < 1
        ):
            raise ValueError("Invalid category state/version")
        key = name_key(row["label"])
        if row["id"] in ids or key in names:
            raise ValueError("Duplicate category ID/name")
        ids.add(row["id"])
        names.add(key)
    return ids


class Conflict(ValueError):
    pass


class TextContent(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text_contract(html, source):
    """Offsets count Unicode code points in reader-body.textContent, including whitespace."""
    parser = TextContent()
    parser.feed(html)
    return {
        "text": "".join(parser.parts),
        "revision": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def resolve_anchor(item, document):
    """Resolve for display only; changed revisions never use nearest-offset guesses."""

    def result(reason, start=None):
        return {
            "status": "unresolved" if start is None else "resolved",
            "reason": reason,
            "start": start,
            "end": None if start is None else start + len(item["quote"]),
            "revision": document["revision"] if document else None,
        }

    if document is None:
        return result("unavailable")
    text, quote = document["text"], item["quote"]
    if document["revision"] == item["revision"]:
        start = item["start"]
        if text[start : item["end"]] == quote:
            return result("current", start)
        return result("context-changed")
    matching = None
    occurrences = 0
    position = 0
    while (start := text.find(quote, position)) != -1:
        occurrences += 1
        end = start + len(quote)
        prefix, suffix = item["prefix"], item["suffix"]
        # Short context reaches the original boundary; added text there needs manual repair.
        before = text[max(0, start - len(prefix)) : start] == prefix and (
            len(prefix) == 120 or start == len(prefix)
        )
        after = text.startswith(suffix, end) and (
            len(suffix) == 120 or end + len(suffix) == len(text)
        )
        if before and after:
            if matching is not None:
                return result("ambiguous")
            matching = start
        position = start + 1
    if matching is not None:
        return result("reattached", matching)
    return result(
        "missing" if occurrences == 0 else "ambiguous" if occurrences > 1 else "context-changed"
    )


def validate(item, *, metadata=True):
    fields = {
        "id",
        "document_id",
        "revision",
        "start",
        "end",
        "quote",
        "prefix",
        "suffix",
        "color",
        "tags",
        "created_at",
        "updated_at",
        "version",
    }
    if metadata:
        fields |= {"title", "description"}
    if not isinstance(item, dict) or set(item) != fields:
        raise ValueError("Invalid annotation fields")
    if not isinstance(item["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", item["id"]):
        raise ValueError("Invalid annotation ID")
    document = safe_text(item["document_id"], 2000).split(":", 2)
    if len(document) != 3 or document[0] not in {"documentation", "note", "journal", "task"}:
        raise ValueError("Invalid document ID")
    if not SLUG.fullmatch(document[1]) or not document[2]:
        raise ValueError("Invalid document source")
    if not isinstance(item["revision"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["revision"]):
        raise ValueError("Invalid source revision")
    if any(type(item[key]) is not int for key in ["start", "end", "version"]):
        raise ValueError("Invalid annotation offsets/version")
    quote = safe_text(item["quote"], 4000)
    if not quote.strip() or not 0 <= item["start"] < item["end"] <= 2_000_000:
        raise ValueError("Invalid selection")
    if item["end"] - item["start"] != len(quote) or item["version"] < 1:
        raise ValueError("Inconsistent selection/version")
    for key in ["prefix", "suffix"]:
        safe_text(item[key], 120)
    if metadata:
        safe_text(item["title"], 120)
        safe_text(item["description"], 1000)
    if not isinstance(item["color"], str) or item["color"] not in COLORS:
        raise ValueError("Invalid annotation color")
    tags = item["tags"]
    if not isinstance(tags, list) or len(tags) > 20:
        raise ValueError("Invalid fragment tags")
    if any(not isinstance(tag, str) or not SLUG.fullmatch(tag) for tag in tags):
        raise ValueError("Tags must be stable category IDs")
    if len(set(tags)) != len(tags):
        raise ValueError("Duplicate fragment tags")
    for key in ["created_at", "updated_at"]:
        timestamp = datetime.fromisoformat(safe_text(item[key], 100))
        if timestamp.utcoffset() is None:
            raise ValueError("Timestamp requires timezone")
    return item


def decode(raw):
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Annotation store exceeds size limit")
    try:
        data = json.loads(raw)
    except RecursionError as error:
        raise ValueError("Annotation JSON is nested too deeply") from error
    if not isinstance(data, dict):
        raise ValueError("Invalid annotation export")
    schema = data.get("schema_version")
    if type(schema) is not int or schema not in {1, 2, 3, 4}:
        raise ValueError("Unsupported annotation schema")
    fields = {"schema_version", "items"} | ({"categories"} if schema >= 2 else set())
    if schema == 4:
        fields.add("scope")
        if data.get("scope") != "work":
            raise ValueError("Unsupported annotation scope")
    if set(data) != fields:
        raise ValueError("Invalid annotation export")
    items = data["items"]
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError("Too many annotations")
    for item in items:
        validate(item, metadata=schema >= 3)
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Duplicate annotation IDs")
    if schema == 1:
        categories = default_categories()
        known = {row["id"] for row in categories}
        for item in items:
            for tag in item["tags"]:
                if tag not in known:
                    categories.append(
                        {
                            "id": tag,
                            "label": tag,
                            "color": item["color"],
                            "archived": False,
                            "version": 1,
                        }
                    )
                    known.add(tag)
        data = {**data, "schema_version": 2, "categories": categories}
    known = validate_categories(data["categories"])
    if any(tag not in known for item in items for tag in item["tags"]):
        raise ValueError("Annotation references an unknown category")
    if schema < 3:
        data = {
            **data,
            "schema_version": 3,
            "items": [{**item, "title": "", "description": ""} for item in items],
        }
    return data


class Annotations:
    def __init__(self, brain):
        self.brain = brain
        self.lock = FileLock(scoped_path(brain.state, "annotations.lock"), timeout=5)

    def _read(self):
        self.brain.ledger()
        path = scoped_path(self.brain.state, "annotations.json")
        if not path.exists():
            data = {"schema_version": 3, "items": [], "categories": default_categories()}
            if self.brain.scope == "work":
                data.update(schema_version=4, scope="work")
            return data
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Annotation store exceeds size limit")
        return self._decode(path.read_text(encoding="utf-8"))

    def _decode(self, raw):
        data = decode(raw)
        if data.get("scope", "personal") != self.brain.scope:
            raise ValueError("Annotation scope does not match deployment")
        return data

    def _write(self, data, previous):
        self.brain.ledger()
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        self._decode(raw)
        if previous is not None:
            current = scoped_path(self.brain.state, "annotations.json")
            atomic_write(
                scoped_path(self.brain.state, "annotations.previous.json"),
                current.read_bytes().decode("utf-8")
                if current.exists()
                else json.dumps(previous, ensure_ascii=False, indent=2),
            )
        atomic_write(scoped_path(self.brain.state, "annotations.json"), raw)

    def export(self):
        with self.lock:
            return self._read()

    def categories(self):
        with self.lock:
            data = self._read()
            return {
                "items": [
                    {**row, "uses": sum(row["id"] in item["tags"] for item in data["items"])}
                    for row in data["categories"]
                ]
            }

    def save_category(self, payload, category_id=None):
        fields = (
            {"label", "color"} if category_id is None else {"label", "color", "archived", "version"}
        )
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError("Invalid category request")
        row = {
            "id": category_id or secrets.token_hex(16),
            "archived": False,
            "version": 1,
            **payload,
            "label": category_name(payload["label"]),
        }
        validate_categories([row])
        with self.lock:
            data = self._read()
            previous = json.loads(json.dumps(data))
            if category_id is not None:
                old = next((r for r in data["categories"] if r["id"] == category_id), None)
                if old is None:
                    raise ValueError("Category is unavailable")
                if old["version"] != payload["version"]:
                    raise Conflict("Category was changed by another request")
                row["version"] += 1
                data["categories"][data["categories"].index(old)] = row
            else:
                data["categories"].append(row)
            self._write(data, previous)
        return row

    def restore(self, raw):
        data = self._decode(raw)
        with self.lock:
            try:
                previous = self._read()
            except (ValueError, UnicodeError):
                # Preserve the last good backup while replacing a corrupt current store.
                previous = None
            self._write(data, previous)
        return {"status": "restored", "count": len(data["items"])}

    def save(self, document, payload, annotation_id=None):
        required = {"document_id", "revision", "start", "end", "quote", "color", "tags"}
        required |= {"version"} if annotation_id else set()
        if (
            not isinstance(payload, dict)
            or not required <= set(payload)
            or set(payload) - required - {"title", "description"}
        ):
            raise ValueError("Invalid annotation request")
        if payload["document_id"] != document["item"]["id"]:
            raise ValueError("Document mismatch")
        if payload["revision"] != document["revision"]:
            raise Conflict("Source changed; reload before saving")
        now = self.brain.now().isoformat()
        item = {
            "title": "",
            "description": "",
            **payload,
            "id": annotation_id or secrets.token_hex(16),
            "version": payload.get("version", 1),
            "prefix": "",
            "suffix": "",
            "created_at": now,
            "updated_at": now,
        }
        validate(item)
        start, end, text = item["start"], item["end"], document["text"]
        if text[start:end] != item["quote"]:
            raise Conflict("Selection no longer matches the reader text")
        item.update(prefix=text[max(0, start - 120) : start], suffix=text[end : end + 120])
        validate(item)
        with self.lock:
            data = self._read()
            previous = json.loads(json.dumps(data))
            if annotation_id:
                old = next((row for row in data["items"] if row["id"] == annotation_id), None)
                if old is None or old["document_id"] != item["document_id"]:
                    raise ValueError("Annotation is unavailable for this document")
                if old["version"] != payload["version"]:
                    raise Conflict("Annotation was changed by another request")
                for key in ["title", "description"]:
                    if key not in payload:
                        item[key] = old[key]
                item.update(created_at=old["created_at"], version=old["version"] + 1)
                data["items"][data["items"].index(old)] = item
            else:
                data["items"].append(item)
                old = None
            categories = {row["id"]: row for row in data["categories"]}
            for tag in item["tags"]:
                if tag not in categories or (
                    categories[tag]["archived"] and (old is None or tag not in old["tags"])
                ):
                    raise ValueError("Select an active fragment category")
            self._write(data, previous)
        return item

    def save_details(self, annotation_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"version", "title", "description"}:
            raise ValueError("Invalid annotation details request")
        if type(payload["version"]) is not int:
            raise ValueError("Invalid annotation version")
        with self.lock:
            data = self._read()
            old = next((row for row in data["items"] if row["id"] == annotation_id), None)
            if old is None:
                raise ValueError("Annotation is unavailable")
            if old["version"] != payload["version"]:
                raise Conflict("Annotation was changed by another request")
            item = validate(
                {
                    **old,
                    **payload,
                    "version": old["version"] + 1,
                    "updated_at": self.brain.now().isoformat(),
                }
            )
            self._write(
                {
                    **data,
                    "items": [item if row["id"] == annotation_id else row for row in data["items"]],
                },
                data,
            )
        return item

    def delete(self, annotation_id, version, *, retain=False):
        if type(version) is not int:
            raise ValueError("Invalid annotation version")
        with self.lock:
            data = self._read()
            old = next((row for row in data["items"] if row["id"] == annotation_id), None)
            if old is None:
                raise ValueError("Annotation is unavailable")
            if old["version"] != version:
                raise Conflict("Annotation was changed by another request")
            self._write({**data, "items": [row for row in data["items"] if row != old]}, data)
        return old if retain else {"status": "deleted", "id": annotation_id}

    def restore_deleted(self, item):
        """Restore only the server-retained mark, without guessing a new source selection."""
        validate(item)
        with self.lock:
            data = self._read()
            if any(row["id"] == item["id"] for row in data["items"]):
                raise Conflict("Annotation ID already exists")
            restored = {
                **item,
                "version": item["version"] + 1,
                "updated_at": self.brain.now().isoformat(),
            }
            self._write({**data, "items": [*data["items"], restored]}, data)
        return restored
