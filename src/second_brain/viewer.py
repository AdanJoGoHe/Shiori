"""Local capability-scoped reader with a separate protected annotation sidecar."""

import json
import posixpath
import re
import secrets
import socket
import threading
import unicodedata
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from second_brain.annotations import COLORS, Annotations, Conflict, resolve_anchor, text_contract
from second_brain.catalog import Catalog, catalog_diagnostics
from second_brain.core import SLUG, safe_text
from second_brain.workflow import JournalConflict
from second_brain.task_pages import TaskPages, task_key


def normalized(text):
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)
    )


def markdown_body(content):
    if content.startswith("---\n"):
        _, separator, body = content[4:].partition("\n---\n")
        if separator:
            content = body
    return re.sub(
        r"^<!-- (?:event:[a-z0-9-]+|shiori-project:[a-z0-9-]*|shiori-data:[^\n]*) -->\n?",
        "",
        content,
        flags=re.MULTILINE,
    )


def preview_text(content, title):
    body = markdown_body(content).lstrip()
    if body.startswith(f"# {title}\n"):
        body = body.split("\n", 1)[1]
    tokens = MarkdownIt("commonmark", {"html": False}).parse(body)
    return " ".join(
        child.content
        for token in tokens
        for child in token.children or []
        if child.type in ("text", "code_inline")
    ).strip()[:220]


def render(content, row, rows):
    parser = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")
    body = markdown_body(content).lstrip()
    if body.startswith(f"# {row['title']}\n"):
        body = body.split("\n", 1)[1]
    tokens = parser.parse(body)
    headings = []
    by_path = {(r["kind"], r["source"], r["path"]): r["id"] for r in rows}
    by_note = {r["id"].split(":", 2)[2]: r["id"] for r in rows if r["kind"] == "note"}
    note_titles = {r["id"]: r["title"] for r in rows if r["kind"] == "note"}
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            anchor = f"section-{len(headings)}"
            token.attrSet("id", anchor)
            headings.append({"id": anchor, "title": tokens[index + 1].content})
        children = []
        for child in token.children or []:
            if child.type != "text":
                children.append(child)
                continue
            last = 0
            for match in re.finditer(r"\[\[([a-z0-9][a-z0-9-]{0,99})\]\]", child.content):
                target_id = by_note.get(match[1])
                if target_id is None:
                    continue
                text = Token("text", "", 0)
                text.content = child.content[last : match.start()]
                link = Token("link_open", "a", 1)
                link.attrs = {"href": "#", "data-content-id": target_id}
                label = Token("text", "", 0)
                label.content = note_titles[target_id]
                children.extend([text, link, label, Token("link_close", "a", -1)])
                last = match.end()
            if last:
                text = Token("text", "", 0)
                text.content = child.content[last:]
                children.append(text)
            else:
                children.append(child)
        if token.children is not None:
            token.children = children
        for child in token.children or []:
            if child.type != "link_open":
                continue
            if child.attrGet("data-content-id"):
                continue
            href = child.attrGet("href") or ""
            target = urlsplit(href)
            if target.scheme in ("http", "https", "mailto"):
                child.attrSet("target", "_blank")
                child.attrSet("rel", "noopener noreferrer")
            elif not target.scheme and not target.netloc:
                relative = posixpath.normpath(
                    posixpath.join(posixpath.dirname(row["path"]), unquote(target.path))
                )
                resolved = by_path.get((row["kind"], row["source"], relative)) or by_note.get(
                    target.path
                )
                if target.path and resolved:
                    child.attrSet("href", "#")
                    child.attrSet("data-content-id", resolved)
                elif not target.path and target.fragment:
                    # Original Markdown anchors may differ from generated reader anchors.
                    child.attrSet("href", "#reader-body")
                else:
                    child.attrSet("href", "#")
                    child.attrSet("data-unavailable", "true")
            else:
                child.attrSet("href", "#")
                child.attrSet("data-unavailable", "true")
    return {"html": parser.renderer.render(tokens, parser.options, {}), "headings": headings}


class Viewer:
    def __init__(self, brain):
        self.catalog = Catalog(brain)
        self.annotations = Annotations(brain)
        self.tasks = TaskPages(brain)
        self.undo_lock = threading.Lock()
        self.deleted = None

    def items(self, params):
        allowed = {
            "q",
            "view",
            "category",
            "color",
            "kind",
            "source",
            "tag",
            "project",
            "type",
            "status",
            "source_agent",
            "from",
            "to",
            "sort",
            "offset",
        }
        if set(params) - allowed or any(
            len(v) != 1 for k, v in params.items() if k not in {"tag", "category"}
        ):
            raise ValueError("Invalid filters")

        def value(key, default=""):
            return params.get(key, [default])[0]

        fragment_view = value("view", "documents") == "fragments"
        if value("view", "documents") not in {"documents", "fragments"}:
            raise ValueError("Invalid view")
        categories = params.get("category", [])
        if len(categories) > 20 or any(
            c != "__none__" and not SLUG.fullmatch(c) for c in categories
        ):
            raise ValueError("Invalid fragment categories")
        color = value("color")
        if color and color not in COLORS:
            raise ValueError("Invalid fragment color")
        if not fragment_view and (categories or color):
            raise ValueError("Fragment filters require fragment view")
        marks = self.annotations.export() if fragment_view else {"items": [], "categories": []}
        by_document = {}
        for mark in marks["items"]:
            by_document.setdefault(mark["document_id"], []).append(mark)
        category_labels = {c["id"]: c["label"] for c in marks["categories"]}
        query = safe_text(value("q"), 300)
        kind, source = value("kind"), value("source")
        sort = value("sort", "relevance")
        if sort not in ("relevance", "updated", "title"):
            raise ValueError("Invalid ordering")
        offset = int(value("offset", "0"))
        if not 0 <= offset <= self.catalog.MAX_ENTRIES:
            raise ValueError("Invalid offset")
        start, end = value("from"), value("to")
        for day in [start, end]:
            if day:
                date.fromisoformat(day)
        if start and end and start > end:
            raise ValueError("Invalid date range")
        tags = params.get("tag", [])
        if len(tags) > 20:
            raise ValueError("Too many tags")
        tags = [safe_text(t, 100).strip().casefold() for t in tags]
        snapshot = self.catalog.snapshot(kind or None, source or None)
        rows = list(snapshot["items"])
        if fragment_view and not snapshot["truncated"]:
            known = {row["id"] for row in rows}
            for document_id in by_document.keys() - known:
                mark_kind, mark_source, identifier = document_id.split(":", 2)
                permitted = (
                    mark_kind == "documentation"
                    and mark_source in self.catalog.brain.config.get("documentation_roots", {})
                ) or (
                    mark_kind in {"note", "journal", "task"}
                    and mark_source == self.catalog.brain.scope
                )
                if (
                    not permitted
                    or (kind and kind != mark_kind)
                    or (source and source != mark_source)
                ):
                    continue
                # Retained quotes only: never read a path absent from the current catalog.
                rows.append(
                    {
                        "id": document_id,
                        "kind": mark_kind,
                        "source": mark_source,
                        "path": identifier,
                        "title": "Documento no disponible: " + identifier,
                        "created_at": None,
                        "updated_at": None,
                        "metadata": {},
                        "available": False,
                    }
                )
        facets = {
            key: sorted(
                {str(r["metadata"][key]) for r in rows if r["metadata"].get(key) is not None}
            )
            for key in ["project", "type", "status", "source_agent"]
        }
        facets["tag"] = sorted({tag for row in rows for tag in row["metadata"].get("tags") or []})
        # Source choices must survive an empty/failed collection and selecting another root.
        sources = (
            set(self.catalog.brain.config.get("documentation_roots", {}))
            if kind in {"", "documentation"}
            else set()
        )
        if kind != "documentation":
            sources.add(self.catalog.brain.scope)
        facets["source"] = sorted(sources)
        facets["category"] = marks["categories"]
        terms = normalized(query).split()
        matches = []
        failed_ids = set()
        for row in rows:
            if fragment_view and row["id"] not in by_document:
                continue
            metadata = row["metadata"]
            if any(
                (
                    metadata.get(key) is not None
                    if value(key) == "__none__"
                    else str(metadata.get(key)) != value(key)
                )
                for key in ["project", "type", "status", "source_agent"]
                if value(key)
            ):
                continue
            row_tags = metadata.get("tags") or []
            if any((bool(row_tags) if t == "__none__" else t not in row_tags) for t in tags):
                continue
            day = (row["updated_at"] or "")[:10]
            if ((start or end) and not day) or (start and day < start) or (end and day > end):
                continue
            try:
                if row.get("available", True):
                    _, content = self.catalog.read(row["id"], snapshot)
                else:
                    content = None
                if fragment_view:
                    document = None
                    for mark in by_document.get(row["id"], []):
                        if color and mark["color"] != color:
                            continue
                        if any(
                            bool(mark["tags"]) if c == "__none__" else c not in mark["tags"]
                            for c in categories
                        ):
                            continue
                        searchable = normalized(
                            mark["quote"]
                            + "\n"
                            + mark["title"]
                            + "\n"
                            + mark["description"]
                            + "\n"
                            + " ".join(category_labels[c] for c in mark["tags"])
                        )
                        if not all(term in searchable for term in terms):
                            continue
                        if document is None and content is not None:
                            rendered = render(content, row, snapshot["items"])
                            document = text_contract(rendered["html"], content)
                        anchor = resolve_anchor(mark, document)
                        if anchor["status"] == "resolved":
                            before = document["text"][
                                max(0, anchor["start"] - 80) : anchor["start"]
                            ]
                            after = document["text"][anchor["end"] : anchor["end"] + 80]
                        else:
                            before, after = mark["prefix"][-80:], mark["suffix"][:80]
                        matches.append(
                            {
                                **row,
                                "annotation": {**mark, "anchor": anchor},
                                "context_before": before,
                                "context_after": after,
                                "score": sum(term in normalized(mark["quote"]) for term in terms),
                            }
                        )
                    continue
                body = markdown_body(content)
                searchable = normalized(row["title"] + "\n" + body)
                if not all(term in searchable for term in terms):
                    continue
                score = sum(3 if term in normalized(row["title"]) else 1 for term in terms)
                preview = preview_text(content, row["title"])
                matches.append({**row, "preview": preview, "score": score})
            except (OSError, ValueError):
                failed_ids.add(row["id"])
                snapshot["errors"].append(
                    {"kind": row["kind"], "source": row["source"], "code": "content-changed"}
                )

        def result_id(row):
            return (row["id"], row.get("annotation", {}).get("id", ""))

        if sort == "title":
            matches.sort(key=lambda r: (normalized(r["title"]), result_id(r)))
        elif sort == "updated":
            matches.sort(key=lambda r: (r["updated_at"] or "", result_id(r)), reverse=True)
        else:
            matches.sort(key=lambda r: (-r["score"], normalized(r["title"]), result_id(r)))
        diagnostics = catalog_diagnostics(
            [row for row in snapshot["items"] if row["id"] not in failed_ids],
            snapshot["errors"],
            snapshot["truncated"],
            {(s["kind"], s["source"]) for s in snapshot["diagnostics"]["sources"]},
            snapshot["diagnostics"]["registered_notes"],
        )
        diagnostics["store_id"] = snapshot["diagnostics"]["store_id"]
        return {
            "items": matches[offset : offset + 20],
            "total": len(matches),
            "next_offset": offset + 20 if offset + 20 < len(matches) else None,
            "facets": facets,
            "errors": snapshot["errors"],
            "truncated": snapshot["truncated"],
            "diagnostics": diagnostics,
            "result_state": "ready"
            if matches
            else diagnostics["status"]
            if diagnostics["status"] in {"limited", "partial", "unavailable"}
            else "empty-catalog"
            if not diagnostics["catalog_items"]
            else "no-matches",
        }

    def content(self, content_id):
        snapshot = self.catalog.snapshot()
        row, body = self.catalog.read(content_id, snapshot)
        related = [
            r
            for r in snapshot["items"]
            if r["kind"] == "note"
            and r["id"].split(":", 2)[2] in (row["metadata"].get("related") or [])
        ]
        rendered = render(body, row, snapshot["items"])
        return {
            "item": row,
            **rendered,
            **text_contract(rendered["html"], body),
            "related": related,
        }

    def annotation_items(self, document_id):
        safe_text(document_id, 2000)
        items = [
            item
            for item in self.annotations.export()["items"]
            if item["document_id"] == document_id
        ]
        try:
            document = self.content(document_id)
        except (ValueError, OSError, UnicodeError):
            if not items:
                raise ValueError("Content is not available in the catalog") from None
            document = None
        return {"items": [{**item, "anchor": resolve_anchor(item, document)} for item in items]}

    def save_annotation(self, payload, annotation_id=None):
        if (
            annotation_id
            and isinstance(payload, dict)
            and set(payload) == {"version", "title", "description"}
        ):
            return self.annotations.save_details(annotation_id, payload)
        if not isinstance(payload, dict) or not isinstance(payload.get("document_id"), str):
            raise ValueError("A catalog document ID is required")
        return self.annotations.save(self.content(payload["document_id"]), payload, annotation_id)

    def delete_annotation(self, annotation_id, version):
        with self.undo_lock:
            item = self.annotations.delete(annotation_id, version, retain=True)
            token = secrets.token_hex(16)
            self.deleted = (token, item)
        return {"status": "deleted", "id": annotation_id, "undo_token": token}

    def undo_annotation(self, payload):
        if (
            not isinstance(payload, dict)
            or set(payload) != {"token"}
            or not isinstance(payload["token"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", payload["token"])
        ):
            raise ValueError("Undo requires its token")
        with self.undo_lock:
            if self.deleted is None or not secrets.compare_digest(
                self.deleted[0], payload["token"]
            ):
                raise Conflict("Undo is no longer available")
            result = self.annotations.restore_deleted(self.deleted[1])
            self.deleted = None
        return result


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR permits a second listener; Unix needs it for prompt restart.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, brain, port=0):
        if not 0 <= port <= 65535:
            raise ValueError("Invalid viewer port")
        self.viewer = Viewer(brain)
        self.prefix = "/" + secrets.token_urlsafe(24)
        super().__init__(("127.0.0.1", port), ViewerHandler)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server_port}"

    @property
    def url(self):
        return self.origin + self.prefix + "/"


class ViewerHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Queries, private paths and the session capability stay out of access logs.

    def reply(self, status, content, mime="application/json; charset=utf-8"):
        data = (
            content
            if isinstance(content, bytes)
            else json.dumps(content, ensure_ascii=False).encode("utf-8")
        )
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; font-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        try:
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def authorized(self, write=False):
        origin = self.server.origin
        valid = (
            self.headers.get_all("Host") == [origin.removeprefix("http://")]
            and self.headers.get_all("Origin", [origin] if not write else []) == [origin]
            and self.headers.get("Sec-Fetch-Site")
            not in ({"cross-site", "same-site"} if write else {"cross-site"})
        )
        if not valid:
            self.reply(403, {"error": "Acceso no permitido."})
        return valid

    def do_GET(self):
        if not self.authorized():
            return
        parsed = urlsplit(self.path)
        prefix = self.server.prefix + "/"
        if not parsed.path.startswith(prefix) or len(self.path) > 5000:
            self.reply(404, {"error": "Contenido no disponible."})
            return
        route = parsed.path[len(prefix) :]
        try:
            if (
                route in ("", "app.js", "journal.js", "style.css", "theme.js", "highlights.js")
                and not parsed.query
            ):
                name = route or "index.html"
                mime = {
                    "index.html": "text/html",
                    "app.js": "text/javascript",
                    "journal.js": "text/javascript",
                    "theme.js": "text/javascript",
                    "highlights.js": "text/javascript",
                    "style.css": "text/css",
                }[name]
                self.reply(
                    200,
                    files("second_brain").joinpath("web", name).read_bytes(),
                    mime + "; charset=utf-8",
                )
            elif route == "api/tasks":
                args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=1)
                if set(args) != {"key"} or len(args["key"]) != 1:
                    raise ValueError("An exact task code is required")
                item = self.server.viewer.tasks.read(task_key(args["key"][0]))
                rows = self.server.viewer.catalog.snapshot()["items"]
                allowed = {row["id"] for row in rows}
                marks = self.server.viewer.annotations.export()["items"]
                links = []
                for link in item["links"]:
                    external = urlsplit(link["target"]).scheme in {"http", "https"}
                    available = external or link["target"] in allowed
                    if link["annotation_id"]:
                        available = available and any(
                            mark["id"] == link["annotation_id"]
                            and mark["document_id"] == link["target"]
                            for mark in marks
                        )
                    links.append({**link, "available": available, "external": external})
                self.reply(200, {"item": item, "links": links})
            elif route == "api/viewer-info":
                if parsed.query:
                    raise ValueError("Viewer info takes no parameters")
                brain = self.server.viewer.catalog.brain
                self.reply(200, {"scope": brain.scope, "today": brain.now().date().isoformat()})
            elif route in {"api/journal", "api/journal-state", "api/project-resume"}:
                from second_brain.workflow import timeline, overview, resume_project

                args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=5)
                allowed = (
                    {"project", "offset", "start_date", "end_date"}
                    if route == "api/journal"
                    else {"project", "offset"}
                    if route == "api/journal-state"
                    else {"project"}
                )
                if set(args) - allowed or any(len(values) != 1 for values in args.values()):
                    raise ValueError("Invalid journal query")
                values = {key: value[0] for key, value in args.items() if value[0]}
                if "offset" in values:
                    values["offset"] = int(values["offset"])
                function = (
                    timeline
                    if route == "api/journal"
                    else overview
                    if route == "api/journal-state"
                    else resume_project
                )
                self.reply(200, function(self.server.viewer.catalog.brain, **values))
            elif route == "api/items":
                self.reply(
                    200,
                    self.server.viewer.items(
                        parse_qs(parsed.query, keep_blank_values=True, max_num_fields=64)
                    ),
                )
            elif route == "api/content":
                args = parse_qs(parsed.query, max_num_fields=2)
                if set(args) != {"id"} or len(args["id"]) != 1:
                    raise ValueError("Invalid content request")
                self.reply(200, self.server.viewer.content(args["id"][0]))
            elif route == "api/categories":
                if parsed.query:
                    raise ValueError("Category listing does not accept filters")
                self.reply(200, self.server.viewer.annotations.categories())
            elif route == "api/annotations":
                args = parse_qs(parsed.query, max_num_fields=2)
                if set(args) != {"document_id"} or len(args["document_id"]) != 1:
                    raise ValueError("Invalid annotation listing")
                self.reply(200, self.server.viewer.annotation_items(args["document_id"][0]))
            else:
                self.reply(404, {"error": "Contenido no disponible."})
        except (ValueError, OSError, KeyError, TypeError, RecursionError):
            self.reply(
                400,
                {
                    "error": "No se puede abrir el contenido o aplicar esos filtros. Actualiza el catálogo."
                },
            )

    def deny_write(self):
        self.reply(405, {"error": "Visor de solo lectura."})

    def mutate_annotation(self):
        parsed = urlsplit(self.path)
        category_route = parsed.path == self.server.prefix + "/api/categories"
        undo_route = parsed.path == self.server.prefix + "/api/annotations/undo"
        journal_route = parsed.path == self.server.prefix + "/api/journal"
        tasks_route = parsed.path == self.server.prefix + "/api/tasks"
        if (
            parsed.path != self.server.prefix + "/api/annotations"
            and not category_route
            and not undo_route
            and not journal_route
            and not tasks_route
        ) or len(self.path) > 5000:
            self.deny_write()
            return
        if category_route and self.command == "DELETE":
            self.deny_write()
            return
        if (undo_route or journal_route or tasks_route) and self.command != "POST":
            self.deny_write()
            return
        if not self.authorized(write=True):
            return
        try:
            args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=2)
            if self.command == "POST":
                if args:
                    raise ValueError("Create does not accept an ID")
                annotation_id = None
            else:
                if (
                    set(args) != {"id"}
                    or len(args["id"]) != 1
                    or not (
                        SLUG.fullmatch(args["id"][0])
                        if category_route
                        else re.fullmatch(r"[a-f0-9]{32}", args["id"][0])
                    )
                ):
                    raise ValueError("Invalid annotation ID")
                annotation_id = args["id"][0]
            lengths = self.headers.get_all("Content-Length", [])
            if (
                self.headers.get("Transfer-Encoding") is not None
                or self.headers.get_all("Content-Type") != ["application/json"]
                or len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdigit()
                or not 0 < int(lengths[0]) <= (400000 if tasks_route else 24000)
            ):
                raise ValueError("A bounded JSON body is required")
            self.connection.settimeout(3)
            raw = self.rfile.read(int(lengths[0]))
            if len(raw) != int(lengths[0]):
                raise ValueError("Incomplete JSON body")
            payload = json.loads(raw.decode("utf-8"))
            if tasks_route:
                if not isinstance(payload, dict):
                    raise ValueError("Task payload must be an object")
                existing = {row["id"] for row in self.server.viewer.catalog.snapshot()["items"]}
                marks = self.server.viewer.annotations.export()["items"]
                old_links = []
                if payload.get("version"):
                    old_links = self.server.viewer.tasks.read(payload.get("key"))["links"]
                for link in payload.get("links", []):
                    if link in old_links:
                        continue
                    if not isinstance(link, dict):
                        raise ValueError("Invalid task link")
                    target = link.get("target", "")
                    if urlsplit(target).scheme not in {"http", "https"} and target not in existing:
                        raise ValueError("Link destination is not available")
                    if link.get("annotation_id") and not any(
                        mark["id"] == link["annotation_id"] and mark["document_id"] == target
                        for mark in marks
                    ):
                        raise ValueError("Fragment is not available")
                result = self.server.viewer.tasks.save(payload)
            elif journal_route:
                brain = self.server.viewer.catalog.brain
                if (
                    not isinstance(payload, dict)
                    or payload.get("mode") != "journal-only"
                    or payload.get("source_agent") != "manual"
                    or payload.get("scope") != brain.scope
                ):
                    raise ValueError(
                        "Viewer writes journal-only manual events in its configured scope"
                    )
                result = brain.capture(payload)
            elif undo_route:
                result = self.server.viewer.undo_annotation(payload)
            elif category_route:
                result = self.server.viewer.annotations.save_category(payload, annotation_id)
            elif self.command == "DELETE":
                if not isinstance(payload, dict) or set(payload) != {"version"}:
                    raise ValueError("Delete requires the current version")
                result = self.server.viewer.delete_annotation(annotation_id, payload["version"])
            else:
                result = self.server.viewer.save_annotation(payload, annotation_id)
            self.reply(201 if self.command == "POST" else 200, result)
        except (Conflict, JournalConflict):
            self.reply(409, {"error": "Los datos han cambiado. Actualiza antes de guardar."})
        except (ValueError, OSError, TypeError, KeyError, RecursionError):
            self.reply(
                400,
                {
                    "error": "No se pudo guardar. Revisa el nombre, duplicados, selección y datos; actualiza si han cambiado."
                },
            )
        finally:
            self.close_connection = True

    do_POST = do_PATCH = do_DELETE = mutate_annotation
    do_PUT = do_OPTIONS = deny_write


def serve_viewer(brain, port=0):
    with ViewerServer(brain, port) as server:
        print(server.url, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
