"""Add canonical notes from a recovery bundle without replacing local knowledge."""

import hashlib
import json
from datetime import datetime

from second_brain.backup import local_path, read_bounded, read_bundle
from second_brain.core import TYPES, atomic_write


def import_memory(brain, source, apply=False):
    source = local_path(source)
    if any(
        source.is_relative_to(root) or root.is_relative_to(source)
        for root in (brain.vault, brain.state)
    ):
        raise ValueError("Import source must be separate from vault and state")
    _, files, incoming = read_bundle(source, brain.scope)
    if any(row["status"] != "committed" for row in incoming["events"].values()):
        raise ValueError("Source has pending captures; resolve them before importing notes")
    notes = {}
    for note_id, relative in incoming["notes"].items():
        raw = files[f"vault/{relative}"]
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "operation": "memory-import-v1",
                    "path": relative,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        notes[note_id] = (relative, raw, fingerprint, "import-" + fingerprint)

    with brain.lock:
        ledger = brain.ledger()
        owned = {
            event_id: (relative, fingerprint)
            for relative, _, fingerprint, event_id in notes.values()
        }
        pending = [
            event_id
            for event_id, row in ledger["events"].items()
            if row["status"] != "committed"
            and owned.get(event_id) != (row["path"], row["fingerprint"])
        ]
        if pending:
            return {"status": "blocked", "reason": "pending-captures", "event_ids": sorted(pending)}
        items, additions, journals = [], [], {}
        for note_id, (relative, raw, fingerprint, event_id) in sorted(notes.items()):
            previous = ledger["events"].get(event_id)
            if previous and (previous["path"], previous["fingerprint"]) != (relative, fingerprint):
                raise ValueError("Import event conflicts with an existing event")
            if note_id in ledger["notes"]:
                brain.read(note_id)
                same = brain.path(ledger["notes"][note_id]).read_bytes() == raw
                items.append({"id": note_id, "action": "duplicate" if same else "conflict"})
                continue
            path = brain.path(relative)
            occupied = [
                brain.path(f"{folder}/{note_id}.md")
                for folder in set(TYPES.values())
                if brain.path(f"{folder}/{note_id}.md").exists()
            ]
            if occupied and not (
                previous
                and previous["status"] == "pending"
                and occupied == [path]
                and read_bounded(path) == raw
            ):
                items.append({"id": note_id, "action": "conflict", "reason": "unmanaged-path"})
                continue
            if previous and previous["status"] == "committed":
                raise ValueError("Committed import event is missing its note")
            moment = datetime.fromisoformat(previous["at"]) if previous else brain.now()
            journal_relative = f"journal/{moment:%Y}/{moment:%Y-%m-%d}.md"
            journal_path = brain.path(journal_relative)
            if journal_relative not in journals:
                journals[journal_relative] = (
                    read_bounded(journal_path).decode("utf-8")
                    if journal_path.exists()
                    else f"# {moment:%Y-%m-%d}\n"
                )
            additions.append(
                (note_id, relative, raw, fingerprint, event_id, moment, journal_relative)
            )
            items.append({"id": note_id, "action": "add"})

        result = {
            "status": "preview",
            "additions": len(additions),
            "duplicates": sum(row["action"] == "duplicate" for row in items),
            "conflicts": sum(row["action"] == "conflict" for row in items),
            "items": items,
            "excluded": [
                "source-journals",
                "history",
                "annotations",
                "task-pages",
                "source-events",
                "configuration",
            ],
        }
        unfinished = {
            event_id for event_id, row in ledger["events"].items() if row["status"] != "committed"
        } - {row[4] for row in additions}
        if unfinished:
            return {
                **result,
                "status": "blocked",
                "reason": "pending-import-conflict",
                "event_ids": sorted(unfinished),
            }
        if not apply:
            return result
        if (brain.state / "paused").exists():
            return {**result, "status": "blocked", "reason": "paused"}
        for note_id, relative, raw, fingerprint, event_id, moment, journal_relative in additions:
            ledger["events"][event_id] = {
                "status": "pending",
                "fingerprint": fingerprint,
                "path": relative,
                "at": moment.isoformat(timespec="seconds"),
            }
        if additions:
            atomic_write(brain.ledger_path, json.dumps(ledger, indent=2))
        for note_id, relative, raw, fingerprint, event_id, moment, journal_relative in additions:
            # Only new notes (or this exact interrupted import) reach this write.
            atomic_write(brain.path(relative), raw.decode("utf-8"))
            marker = f"<!-- event:{event_id} -->"
            if marker not in journals[journal_relative]:
                journals[journal_relative] += (
                    f"\n{marker}\n## {moment:%H:%M} — Imported memory\n\n"
                    f"- Agent: manual\n- Outcome: Added without replacing existing memory.\n"
                    f"- Knowledge: [[{note_id}]]\n"
                )
            ledger["notes"][note_id] = relative
            ledger["events"][event_id]["status"] = "committed"
        if additions:
            for journal_relative, content in journals.items():
                atomic_write(brain.path(journal_relative), content)
            atomic_write(brain.ledger_path, json.dumps(ledger, indent=2))
        return {**result, "status": "imported"}
