"""Transparent capture decisions from explicit agent assessments; never writes."""

import hashlib
import json

from second_brain.core import safe_text, validate_candidate


def classify_capture(brain, candidate, assessment):
    def result(decision, reason, **extra):
        return {"decision": decision, "reason": reason, **extra}

    if not isinstance(candidate, dict) or candidate.get("scope") != brain.scope:
        return result("deny", f"{brain.scope}-scope-required")
    try:
        safe_text(json.dumps(candidate, ensure_ascii=False), 30000)
    except (ValueError, TypeError):
        return result("deny", "unsafe-or-invalid-candidate")
    if (
        not isinstance(assessment, dict)
        or set(assessment) != {"material", "reusable", "meaningful", "evidence_kind"}
        or type(assessment["reusable"]) is not bool
        or type(assessment["meaningful"]) is not bool
        or assessment["material"] not in ("personal", "corporate", "customer", "unknown")
        or assessment["evidence_kind"] not in ("observed", "source", "user-confirmed", "none")
    ):
        return result("deny", "invalid-assessment")
    material = "personal" if brain.scope == "personal" else "corporate"
    if assessment["material"] != material:
        return result("deny", f"non-{material}-or-unknown-material")
    if not assessment["reusable"] and not assessment["meaningful"]:
        return result("skip", "no-reusable-insight-or-meaningful-progress")
    prepared = dict(candidate)
    warnings = []
    if not isinstance(candidate.get("evidence", ""), str):
        return result("deny", "invalid-capture-fields")
    if not assessment["reusable"] or candidate.get("mode") == "journal-only":
        prepared = {
            key: candidate[key]
            for key in (
                "scope",
                "event_id",
                "title",
                "source_agent",
                "summary",
                "project",
                "progress",
                "activity",
                "supersedes",
                "change_reason",
                "tasks",
            )
            if key in candidate
        }
        prepared["mode"] = "journal-only"
    elif candidate.get("status") == "verified" and (
        assessment["evidence_kind"] == "none" or not candidate.get("evidence", "").strip()
    ):
        prepared["status"] = "unverified"
        warnings.append("verification-not-established")
    try:
        validate_candidate(prepared, brain.scope)
    except (ValueError, TypeError):
        return result("deny", "invalid-capture-fields")
    if (brain.state / "paused").exists():
        return result("skip", "paused")
    # Exact identity only: agents must search related notes before proposing a new ID.
    with brain.lock:
        ledger = brain.ledger()
        previous = ledger["events"].get(prepared["event_id"])
        if previous:
            fingerprint = hashlib.sha256(json.dumps(prepared, sort_keys=True).encode()).hexdigest()
            if previous["fingerprint"] != fingerprint:
                return result("deny", "event-id-payload-conflict")
            if previous["status"] == "committed":
                return result("skip", "duplicate-event")
            warnings.append("pending-event-retry")
        from second_brain.workflow import check_capture, JournalConflict

        try:
            unchanged = check_capture(brain, prepared, previous)
        except JournalConflict:
            return result("deny", "journal-history-or-version-conflict")
        if unchanged:
            return result("skip", "unchanged-activity")
        if prepared.get("mode") == "journal-only":
            return result(
                "journal-only", "meaningful-progress", candidate=prepared, warnings=warnings
            )
        existing = prepared["id"] in ledger["notes"]
        if existing:
            brain.read(prepared["id"])
    return result(
        "update" if existing else "save",
        "reusable-insight",
        candidate=prepared,
        warnings=warnings,
    )
