"""Files are canonical. The ledger stores identifiers, never captured bodies."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from filelock import FileLock

TYPES = {
    "knowledge": "knowledge",
    "command": "commands",
    "troubleshooting": "troubleshooting",
    "decision": "decisions",
    "lesson": "lessons-learned",
    "profile": "profile",
    "preference": "profile",
}
STATUSES = {"verified", "unverified", "superseded", "obsolete", "draft"}
AGENTS = {"codex", "claude-code", "augment-jetbrains", "manual"}
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,99}\Z")
SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[A-Z0-9]{16})\b|"
    r"(?i:authorization\s*:\s*(?:bearer|basic)\s+\S+)|"
    r"(?i:(?:password|passwd|api[_-]?key|access[_-]?token|secret|token)\s*[:=]\s*)"
    r"[\"']?(?!<|\$)[A-Za-z0-9_./+\-=]{4,}|"
    r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"
)


def safe_text(value, maximum=24000):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError("Invalid or oversized text")
    if SECRET.search(value):
        raise ValueError("Possible secret rejected; use placeholders or omit it")
    return value


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".sb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def note_metadata(values, previous=None):
    """Validate curated metadata; omitted fields retain their prior value on update."""
    previous = previous or {}
    result = {}
    for key in ["tags", "source_refs", "related"]:
        items = values.get(key, previous.get(key, []))
        if not isinstance(items, list) or len(items) > 20:
            raise ValueError(f"{key} must be a list of at most 20 strings")
        normalized = []
        for item in items:
            item = safe_text(item, 500 if key == "source_refs" else 100).strip()
            if not item:
                raise ValueError(f"Empty {key} value")
            if key == "tags":
                item = item.casefold()
            if key == "related" and not SLUG.fullmatch(item):
                raise ValueError("Related notes must use stable note IDs")
            if item not in normalized:
                normalized.append(item)
        result[key] = normalized
    project = values.get("project", previous.get("project"))
    if project is not None:
        safe_text(project, 100)
        if not SLUG.fullmatch(project):
            raise ValueError("Project must be a lowercase slug or null")
    result["project"] = project
    sensitivity = values.get("sensitivity", previous.get("sensitivity", "normal"))
    if sensitivity not in ("normal", "restricted", "private"):
        raise ValueError("Invalid sensitivity")
    result["sensitivity"] = sensitivity
    return result


def validate_candidate(candidate):
    if not isinstance(candidate, dict) or candidate.get("scope") != "personal":
        raise ValueError("Candidate must explicitly use personal scope")
    mode = candidate.get("mode", "note")
    if mode not in {"note", "journal-only"}:
        raise ValueError("Invalid capture mode")
    journal_only = mode == "journal-only"
    if journal_only and set(candidate) - {
        "scope",
        "mode",
        "event_id",
        "title",
        "source_agent",
        "summary",
    }:
        raise ValueError("Journal-only captures accept only scope/mode/event/title/agent/summary")
    note_id = candidate.get("id", "")
    event_id = candidate.get("event_id", "")
    safe_text(note_id, 100)
    safe_text(event_id, 100)
    if (not journal_only and not SLUG.fullmatch(note_id)) or not SLUG.fullmatch(event_id):
        raise ValueError("IDs must be lowercase slugs, at most 100 characters")
    kind = candidate.get("type")
    status = candidate.get("status")
    agent = candidate.get("source_agent")
    if agent not in AGENTS or (not journal_only and (kind not in TYPES or status not in STATUSES)):
        raise ValueError("Invalid type, status or agent")
    title = safe_text(candidate.get("title"), 200).strip()
    body = safe_text(
        candidate.get("body", "") if journal_only else candidate.get("body"), 20000
    ).strip()
    evidence = safe_text(candidate.get("evidence", ""), 2000).strip()
    summary = safe_text(candidate.get("summary", "" if journal_only else title), 1000).strip()
    if not title or (journal_only and not summary):
        raise ValueError("Title and journal summary required")
    if not journal_only and (not body or (status == "verified" and not evidence)):
        raise ValueError("Title/body required; verified notes require evidence")
    # Scan every supplied field, including identifiers and optional metadata.
    safe_text(json.dumps(candidate, ensure_ascii=False), 30000)
    if not journal_only:
        note_metadata(candidate)


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if (
        not isinstance(config, dict)
        or config.get("schema_version") != 1
        or config.get("scope") != "personal"
    ):
        raise ValueError("Only personal deployments are enabled in v0.1")
    if not {"vault_path", "state_path", "timezone"}.issubset(config):
        raise ValueError("Incomplete deployment configuration")
    for field in ["vault_path", "state_path", "basic_memory_config_dir"]:
        if field in config and (field != "basic_memory_config_dir" or config[field]):
            config[field] = str(canonical_root(config[field]))
    ZoneInfo(config["timezone"])
    return config


def canonical_root(value):
    if not isinstance(value, (str, Path)):
        raise ValueError("Invalid deployment root")
    root = Path(value)
    if not root.is_absolute():
        raise ValueError("Deployment roots must be absolute")
    if any(p.is_symlink() or p.is_junction() for p in [root, *root.parents]):
        raise ValueError("Linked deployment roots are forbidden")
    return root.resolve()


def initialize_root(value):
    """Resolve a newly initialized namespace using an owned, empty temporary file."""
    root = canonical_root(value)
    root.mkdir(parents=True, exist_ok=True)
    root = canonical_root(root)
    fd, temporary = tempfile.mkstemp(prefix=".sb-root-", dir=root)
    os.close(fd)
    probe = Path(temporary)
    try:
        physical = probe.resolve(strict=True)
        if not probe.samefile(physical):
            raise ValueError("Initialized root identity could not be verified")
        return canonical_root(physical.parent)
    finally:
        probe.unlink()


def scoped_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Path escapes root")
    root = canonical_root(root)
    candidate = root / relative
    for component in [candidate, *candidate.parents]:
        if component == root:
            break
        if component.is_symlink() or component.is_junction():
            raise ValueError("Linked paths are forbidden")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Path escapes root")
    return resolved


def validate_note(content, note_id):
    safe_text(content, 100000)
    if not content.startswith("---\n"):
        raise ValueError("Invalid note frontmatter")
    try:
        metadata = yaml.safe_load(content.split("---", 2)[1])
    except yaml.YAMLError:
        raise ValueError("Invalid YAML metadata; inspect the local note") from None
    if not isinstance(metadata, dict):
        raise ValueError("Invalid note metadata")
    required = {
        "schema_version",
        "id",
        "title",
        "type",
        "scope",
        "status",
        "created_at",
        "updated_at",
        "last_verified_at",
        "source_agent",
        "source_refs",
        "related",
        "tags",
        "sensitivity",
    }
    if not required.issubset(metadata) or metadata["schema_version"] != 1:
        raise ValueError("Unsupported or incomplete note schema")
    if metadata["status"] not in STATUSES or metadata["type"] not in TYPES:
        raise ValueError("Invalid note status/type")
    if metadata["source_agent"] not in AGENTS:
        raise ValueError("Invalid note source agent")
    for key in ["created_at", "updated_at"]:
        if datetime.fromisoformat(str(metadata[key])).tzinfo is None:
            raise ValueError("Timestamps require timezone")
    if metadata.get("scope") != "personal" or metadata.get("id") != note_id:
        raise ValueError("Note metadata does not match deployment")
    note_metadata(metadata)
    return content


class Brain:
    def __init__(self, config):
        if config.get("scope") != "personal":
            raise ValueError("Work deployment is disabled")
        self.config = config
        self.vault = canonical_root(config["vault_path"])
        self.state = canonical_root(config["state_path"])
        self.ledger_path = scoped_path(self.state, "ledger.json")
        if self.ledger_path.exists() and not self.vault.is_dir():
            raise ValueError("Existing deployment vault is unavailable; inspect paths")
        if not self.ledger_path.exists() and self.vault.is_dir():
            managed = [(folder, "*.md") for folder in set(TYPES.values())]
            managed += [("journal", "*/*.md"), ("archive", "*/*.md")]
            if any(
                next(scoped_path(self.vault, folder).glob(pattern), None)
                for folder, pattern in managed
            ):
                raise ValueError("Existing vault requires its ledger; inspect paths")
        if not self.vault.is_dir():
            self.vault = initialize_root(self.vault)
        if not self.state.is_dir():
            self.state = initialize_root(self.state)
        self.ledger_path = scoped_path(self.state, "ledger.json")
        self.lock = FileLock(scoped_path(self.state, "capture.lock"), timeout=5)

    def now(self):
        return datetime.now(ZoneInfo(self.config["timezone"]))

    def path(self, relative):
        return scoped_path(self.vault, relative)

    def ledger(self):
        if self.ledger_path.exists():
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        return {"events": {}, "notes": {}}

    def read(self, note_id):
        if not SLUG.fullmatch(note_id):
            raise ValueError("Invalid note ID")
        ledger = self.ledger()
        if note_id not in ledger["notes"]:
            raise ValueError("Unknown note ID")
        content = self.path(ledger["notes"][note_id]).read_text(encoding="utf-8")
        return validate_note(content, note_id)

    def search(self, query, limit=5, filters=None, *, contextual=False):
        terms = safe_text(query, 300).lower().split()
        filters = {} if filters is None else filters
        if not isinstance(filters, dict) or set(filters) - {
            "tags",
            "project",
            "type",
            "status",
            "source_agent",
        }:
            raise ValueError("Unsupported search filters")
        validated = note_metadata(filters)
        for key, choices in [("type", TYPES), ("status", STATUSES), ("source_agent", AGENTS)]:
            if key in filters and filters[key] not in tuple(choices):
                raise ValueError(f"Invalid {key} filter")
        limit = max(1, min(int(limit), 5))
        results = []
        ranks = {}
        for note_id, relative in self.ledger()["notes"].items():
            content = self.read(note_id)
            metadata = yaml.safe_load(content.split("---", 2)[1])
            curated = note_metadata(metadata)
            if (
                contextual
                and "status" not in filters
                and metadata["status"] in {"obsolete", "superseded"}
            ):
                continue
            if "tags" in filters:
                wanted = validated["tags"]
                if (not wanted and curated["tags"]) or not set(wanted).issubset(curated["tags"]):
                    continue
            if "project" in filters and validated["project"] != curated["project"]:
                continue
            if any(
                metadata[key] != filters[key]
                for key in ["type", "status", "source_agent"]
                if key in filters
            ):
                continue
            searchable = content.lower()
            if contextual:
                body = content.split("---", 2)[2]
                searchable = " ".join(
                    [
                        str(metadata["title"]),
                        note_id,
                        *curated["tags"],
                        curated["project"] or "",
                        body,
                    ]
                ).lower()
                ranks[note_id] = (
                    metadata["status"] != "verified",
                    not bool(body.partition("\n## Evidence\n")[2].strip()),
                    -datetime.fromisoformat(str(metadata["updated_at"])).timestamp(),
                    note_id,
                )
            score = sum(term in searchable for term in terms)
            if score or not terms:
                results.append(
                    {
                        "id": note_id,
                        "path": relative,
                        "score": score,
                        "excerpt": content[:1600],
                        **({"content": content} if contextual else {}),
                    }
                )
                if contextual:
                    results.sort(key=lambda item: (-item["score"], *ranks[item["id"]]))
                    del results[limit:]
        if contextual:
            return results
        return sorted(results, key=lambda item: (-item["score"], item["id"]))[:limit]

    def capture(self, candidate):
        validate_candidate(candidate)
        journal_only = candidate.get("mode", "note") == "journal-only"
        note_id = candidate.get("id", "")
        event_id = candidate["event_id"]
        kind = candidate.get("type")
        status = candidate.get("status")
        agent = candidate["source_agent"]
        title = candidate["title"].strip()
        body = candidate.get("body", "").strip()
        evidence = candidate.get("evidence", "").strip()
        summary = candidate.get("summary", "" if journal_only else title).strip()
        fingerprint = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if (self.state / "paused").exists():
                return {"status": "skipped", "reason": "paused"}
            ledger = self.ledger()
            previous_event = ledger["events"].get(event_id)
            if previous_event:
                if previous_event["fingerprint"] != fingerprint:
                    raise ValueError("Event ID reused for a different payload")
                if previous_event["status"] == "committed":
                    if journal_only:
                        return {"status": "duplicate", "journal": previous_event["path"]}
                    return {"status": "duplicate", "id": note_id, "path": previous_event["path"]}
            if not journal_only:
                # A different event must not overtake an interrupted write to the same note.
                note_paths = {f"{folder}/{note_id}.md" for folder in TYPES.values()}
                for pending_id, pending in ledger["events"].items():
                    if (
                        pending_id != event_id
                        and pending["status"] != "committed"
                        and pending["path"] in note_paths
                    ):
                        return {
                            "status": "blocked",
                            "reason": "pending-note-capture",
                            "id": note_id,
                            "event_id": pending_id,
                        }
            moment = self.now()
            if previous_event:
                moment = datetime.fromisoformat(previous_event["at"])
            timestamp = moment.isoformat(timespec="seconds")
            journal_relative = f"journal/{moment:%Y}/{moment:%Y-%m-%d}.md"
            journal_path = self.path(journal_relative)
            relative = journal_relative
            if not journal_only:
                relative = ledger["notes"].get(note_id, f"{TYPES[kind]}/{note_id}.md")
                note_path = self.path(relative)
                if note_path.exists() and note_id not in ledger["notes"] and not previous_event:
                    raise ValueError("Refusing to overwrite an unmanaged note")
                old = self.read(note_id) if note_id in ledger["notes"] else None
                prior_metadata = yaml.safe_load(old.split("---", 2)[1]) if old else {}
                created = yaml.safe_load(old.split("---", 2)[1])["created_at"] if old else timestamp
                metadata = {
                    "schema_version": 1,
                    "id": note_id,
                    "title": title,
                    "type": kind,
                    "scope": "personal",
                    "status": status,
                    "created_at": created,
                    "updated_at": timestamp,
                    "last_verified_at": timestamp if status == "verified" else None,
                    "source_agent": agent,
                    "source_refs": [],
                    "tags": [],
                    "related": [],
                    "sensitivity": "normal",
                }
                metadata.update(note_metadata(candidate, prior_metadata))
                content = "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
                content += (
                    f"---\n\n# {title}\n\n{body}\n\n## Evidence\n{evidence or 'Not verified'}\n"
                )
                if old and old != content:
                    revision = hashlib.sha256(old.encode()).hexdigest()[:16]
                    history = self.path(f"archive/{note_id}/{revision}.md")
                    if not history.exists():
                        atomic_write(history, old)
            # A pending ledger plus journal marker makes retry after a partial write safe.
            ledger["events"][event_id] = {
                "status": "pending",
                "fingerprint": fingerprint,
                "path": relative,
                "at": timestamp,
            }
            atomic_write(self.ledger_path, json.dumps(ledger, indent=2))
            if not journal_only:
                atomic_write(note_path, content)
            journal = (
                journal_path.read_text(encoding="utf-8")
                if journal_path.exists()
                else f"# {moment:%Y-%m-%d}\n"
            )
            marker = f"<!-- event:{event_id} -->"
            if marker not in journal:
                journal += f"\n{marker}\n## {moment:%H:%M} — {title}\n\n"
                journal += f"- Agent: {agent}\n- Outcome: {summary}\n"
                if not journal_only:
                    journal += f"- Knowledge: [[{note_id}]]\n"
                atomic_write(journal_path, journal)
            if not journal_only:
                ledger["notes"][note_id] = relative
            ledger["events"][event_id]["status"] = "committed"
            atomic_write(self.ledger_path, json.dumps(ledger, indent=2))
            if journal_only:
                return {"status": "saved", "journal": journal_relative}
            return {"status": "saved", "id": note_id, "path": relative, "journal": journal_relative}

    def pending_captures(self, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Offset must be nonnegative; limit must be 1–100")
        with self.lock:
            pending = [
                {
                    "event_id": event_id,
                    **{key: item[key] for key in ("status", "fingerprint", "path", "at")},
                }
                for event_id, item in self.ledger()["events"].items()
                if item["status"] != "committed"
            ]
        return {
            "events": pending[offset : offset + limit],
            "total": len(pending),
            "next_offset": offset + limit if offset + limit < len(pending) else None,
            "retry": "Resubmit the identical original candidate with its original event_id. "
            "Payloads are not retained; never reconstruct them from excerpts.",
        }

    def status(self):
        ledger = self.ledger()
        return {
            "scope": "personal",
            "vault": str(self.vault),
            "notes": len(ledger["notes"]),
            "paused": (self.state / "paused").exists(),
            "pending": sum(e["status"] != "committed" for e in ledger["events"].values()),
        }

    def pause(self, enabled):
        with self.lock:
            if enabled:
                atomic_write(self.state / "paused", "paused\n")
            else:
                (self.state / "paused").unlink(missing_ok=True)
        return self.status()
