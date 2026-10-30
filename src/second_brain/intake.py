"""Explicit, bounded agent input and a single classify/capture transaction."""

import json
import re
import sys
from pathlib import Path

from second_brain.quality import classify_capture


def read_json(source):
    if str(source) == "-":
        if sys.stdin.isatty():
            raise ValueError("Pipe UTF-8 JSON to stdin or supply a file; refusing interactive wait")
        raw = sys.stdin.buffer.read(40001)
    else:
        with Path(source).open("rb") as stream:
            raw = stream.read(40001)
    if not raw or len(raw) > 40000:
        raise ValueError("JSON input must contain 1–40000 bytes")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("Invalid UTF-8 JSON input") from None


def classification_request(request):
    if not isinstance(request, dict) or set(request) != {"candidate", "assessment"}:
        raise ValueError("Request requires only candidate and assessment")
    return request["candidate"], request["assessment"]


def note_flow(brain, request, *, apply=False, expect_revision=None):
    candidate, assessment = classification_request(request)
    if expect_revision is not None and (
        not isinstance(expect_revision, str)
        or not re.fullmatch(r"[a-f0-9]{64}|absent", expect_revision)
    ):
        raise ValueError("Expected revision must be a SHA256 or absent")
    with brain.lock:
        preview = classify_capture(brain, candidate, assessment)
        result = {**preview, "applied": False}
        if preview["decision"] not in {"save", "update", "journal-only"}:
            return result
        prepared = preview["candidate"]
        if prepared.get("mode") != "journal-only":
            result["exact"] = brain.find(prepared["id"])
            result["related"] = brain.search(prepared["title"])
        base = preview.get("diff", {}).get("base_revision", "absent")
        result["base_revision"] = base
        if apply:
            if (
                expect_revision is not None
                and expect_revision != base
                and "pending-event-retry" not in preview["warnings"]
            ):
                return {
                    **result,
                    "capture": {"status": "blocked", "reason": "note-revision-changed"},
                }
            result["capture"] = brain.capture(prepared)
            result["applied"] = result["capture"]["status"] == "saved"
        return result
