"""Read-only, bounded catalog. Roots come from trusted local configuration, not requests."""

import hashlib
import os
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from second_brain.core import SLUG, TYPES, note_metadata, safe_text, scoped_path

KINDS = {"documentation", "note", "journal"}
EXCLUDED = {"archive", "archives", "backups", "runtime", "local", "node_modules", "__pycache__"}
PRIVATE_FILES = {"credentials", "secrets", "passwords", "tokens"}
METADATA = [
    "tags",
    "project",
    "type",
    "status",
    "source_agent",
    "source_refs",
    "related",
    "sensitivity",
]


def catalog_diagnostics(rows, errors, truncated, collections, registered_notes=None):
    sources = []
    for kind, source in sorted(collections):
        readable = sum(r["kind"] == kind and r["source"] == source for r in rows)
        failed = any(e["kind"] == kind and e["source"] == source for e in errors)
        sources.append(
            {
                "kind": kind,
                "source": source,
                "readable": readable,
                "status": ("partial" if readable else "unavailable")
                if failed
                else ("ready" if readable else "empty"),
            }
        )
    codes = {e["code"] for e in errors}
    readable_notes = sum(r["kind"] == "note" for r in rows)
    if not truncated and registered_notes is not None and registered_notes != readable_notes:
        codes.add("ledger-catalog-mismatch")
    if truncated:
        status = "limited"
    elif errors:
        status = (
            "partial" if rows or any(s["status"] == "empty" for s in sources) else "unavailable"
        )
    else:
        status = "ready" if rows else "empty"
    return {
        "status": status,
        "catalog_items": len(rows),
        "registered_notes": registered_notes,
        "readable_notes": readable_notes,
        "sources": sources,
        "codes": sorted(codes),
    }


class Catalog:
    MAX_ENTRIES = 2000
    MAX_BYTES = 1_000_000

    def __init__(self, brain):
        self.brain = brain

    def _root(self, value):
        root = Path(value)
        if not root.is_absolute():
            raise ValueError("Absolute documentation root required")
        if any(p.is_symlink() or p.is_junction() for p in [root, *root.parents]):
            raise ValueError("Linked documentation root")
        root = root.resolve()
        for private in [self.brain.vault, self.brain.state]:
            if root.is_relative_to(private) or private.is_relative_to(root):
                raise ValueError("Documentation must not overlap private roots")
        return root

    def _content(self, root, relative, note_id=None):
        path = scoped_path(root, relative)
        if path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Content too large")
        if note_id:
            content = self.brain.read(note_id)
        else:
            with path.open(encoding="utf-8-sig") as stream:
                content = stream.read(self.MAX_BYTES + 1)
            if len(content) > self.MAX_BYTES:
                raise ValueError("Content too large")
        return content

    def _row(self, root, relative, kind, source, note_id=None):
        path = scoped_path(root, relative)
        content = self._content(root, relative, note_id)
        metadata = {}
        if content.startswith("---\n"):
            frontmatter, separator, _ = content[4:].partition("\n---\n")
            if not separator:
                raise ValueError("Unterminated frontmatter")
            metadata = yaml.safe_load(frontmatter)
            if not isinstance(metadata, dict):
                raise ValueError("Invalid metadata")
        curated = note_metadata(metadata)
        fields = {key: None for key in METADATA}
        for key in METADATA:
            if key in metadata:
                fields[key] = curated[key] if key in curated else safe_text(metadata[key], 100)
        heading = next(
            (line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem
        )
        title = safe_text(metadata.get("title", heading), 200)
        updated = (
            metadata.get("updated_at")
            if note_id
            else datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        )
        row = {
            "id": f"{kind}:{source}:{note_id or Path(relative).as_posix()}",
            "kind": kind,
            "source": source,
            "path": Path(relative).as_posix(),
            "title": title,
            "created_at": metadata.get("created_at") if note_id else None,
            "updated_at": updated,
            "metadata": fields,
        }
        safe_text(str(row), 20000)
        return row

    def snapshot(self, kind=None, source=None):
        if kind is not None and kind not in KINDS:
            raise ValueError("Invalid catalog kind")
        if source is not None and (not isinstance(source, str) or not SLUG.fullmatch(source)):
            raise ValueError("Source must be a configured source ID")
        roots = self.brain.config.get("documentation_roots", {})
        if (
            not isinstance(roots, dict)
            or len(roots) > 10
            or any(
                not isinstance(key, str) or not SLUG.fullmatch(key) or not isinstance(value, str)
                for key, value in roots.items()
            )
        ):
            raise ValueError("Invalid documentation roots configuration")
        if source is not None and source not in {"personal", *roots}:
            raise ValueError("Unknown catalog source")
        rows, errors = [], []
        collections = set()
        registered_notes = None
        visited = 0
        truncated = False

        def error(content_kind, content_source, code):
            value = {"kind": content_kind, "source": content_source, "code": code}
            if value not in errors and len(errors) < 50:
                errors.append(value)

        def reserve(content_kind, content_source):
            nonlocal visited, truncated
            if visited >= self.MAX_ENTRIES:
                truncated = True
                error(content_kind, content_source, "scan-limit")
                return False
            visited += 1
            return True

        def files(root, directory, content_kind, content_source):
            pending = [directory]
            while pending:
                try:
                    selected = []
                    with os.scandir(pending.pop()) as entries:
                        for entry in entries:
                            if not reserve(content_kind, content_source):
                                break
                            selected.append(Path(entry.path))
                    for path in sorted(selected):
                        if path.name.startswith(".") or path.name.casefold() in EXCLUDED:
                            continue
                        if path.is_symlink() or path.is_junction():
                            error(content_kind, content_source, "linked-path")
                            continue
                        path = scoped_path(root, path.relative_to(root))
                        if path.is_dir():
                            pending.append(path)
                        elif (
                            path.suffix.casefold() == ".md"
                            and path.stem.casefold() not in PRIVATE_FILES
                        ):
                            yield path.relative_to(root)
                except OSError:
                    error(content_kind, content_source, "unavailable")
                except ValueError:
                    error(content_kind, content_source, "linked-path")

        def append(root, relative, content_kind, content_source, note_id=None):
            try:
                rows.append(self._row(root, relative, content_kind, content_source, note_id))
            except (OSError, ValueError, TypeError, KeyError, RecursionError, yaml.YAMLError):
                error(content_kind, content_source, "invalid-content")

        if kind in (None, "documentation"):
            for name, value in sorted(roots.items()):
                if source is not None and source != name:
                    continue
                collections.add(("documentation", name))
                try:
                    root = self._root(value)
                except (OSError, ValueError):
                    error("documentation", name, "invalid-root")
                    continue
                for relative in files(root, root, "documentation", name):
                    append(root, relative, "documentation", name)
        if source in (None, "personal"):
            if kind in (None, "note"):
                collections.add(("note", "personal"))
                try:
                    notes = self.brain.ledger()["notes"]
                    if not isinstance(notes, dict):
                        raise ValueError("Invalid notes registry")
                    registered_notes = len(notes)
                    for note_id, relative in sorted(notes.items()):
                        if not reserve("note", "personal"):
                            break
                        parts = Path(relative).parts if isinstance(relative, str) else ()
                        if not parts or parts[0] not in TYPES.values():
                            error("note", "personal", "invalid-content")
                            continue
                        append(self.brain.vault, relative, "note", "personal", note_id)
                except (OSError, ValueError, KeyError, TypeError):
                    error("note", "personal", "unavailable")
            if kind in (None, "journal"):
                collections.add(("journal", "personal"))
                try:
                    root = self.brain.path("journal")
                    if root.exists():
                        for relative in files(root, root, "journal", "personal"):
                            try:
                                day = date.fromisoformat(relative.stem)
                            except ValueError:
                                continue
                            if relative.as_posix() != f"{day.year}/{day.isoformat()}.md":
                                continue
                            append(root, relative, "journal", "personal")
                except (OSError, ValueError):
                    error("journal", "personal", "unavailable")
        rows.sort(key=lambda row: (row["kind"], row["source"], row["path"]))
        diagnostics = catalog_diagnostics(rows, errors, truncated, collections, registered_notes)
        try:
            diagnostics["store_id"] = hashlib.sha256(
                str((self.brain.vault.resolve(), self.brain.state.resolve())).encode()
            ).hexdigest()[:16]
        except (OSError, ValueError):
            diagnostics["store_id"] = None
        return {
            "items": rows,
            "errors": errors,
            "truncated": truncated,
            "diagnostics": diagnostics,
        }

    def list(self, kind=None, source=None, offset=0, limit=25):
        if type(offset) is not int or not 0 <= offset <= self.MAX_ENTRIES:
            raise ValueError("Invalid catalog offset")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Catalog limit must be between 1 and 100")
        result = self.snapshot(kind, source)
        end = offset + limit
        rows = result["items"]
        return {
            **result,
            "items": rows[offset:end],
            "next_offset": end if end < len(rows) else None,
        }

    def read(self, content_id, snapshot=None):
        """Resolve only currently cataloged IDs; callers never choose filesystem paths."""
        safe_text(content_id, 2000)
        rows = (snapshot if snapshot is not None else self.snapshot())["items"]
        row = next((item for item in rows if item["id"] == content_id), None)
        if row is None:
            raise ValueError("Content is not available in the catalog")
        if row["kind"] == "documentation":
            root = self._root(self.brain.config["documentation_roots"][row["source"]])
            content = self._content(root, row["path"])
        elif row["kind"] == "note":
            content = self._content(self.brain.vault, row["path"], content_id.split(":", 2)[2])
        else:
            content = self._content(self.brain.path("journal"), row["path"])
        return row, content
