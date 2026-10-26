import asyncio
import copy
import json
import subprocess
import sys

import pytest
from fastmcp import Client

from second_brain.quality import classify_capture
from test_core import brain as brain, event


def assessment(**changes):
    return dict(
        material="personal", reusable=True, meaningful=True, evidence_kind="observed", **changes
    )


@pytest.mark.parametrize(
    "changes,signals,decision,status",
    [
        ({}, {}, "save", "verified"),
        (
            {"type": "lesson", "body": "Failed approach: it assumes a writable folder."},
            {},
            "save",
            "verified",
        ),
        (
            {"type": "preference", "body": "User explicitly prefers concise Spanish."},
            {"evidence_kind": "user-confirmed"},
            "save",
            "verified",
        ),
        ({}, {"evidence_kind": "source"}, "save", "verified"),
        ({}, {"evidence_kind": "none"}, "save", "unverified"),
        ({"evidence": "   "}, {}, "save", "unverified"),
        ({"status": "draft", "evidence": ""}, {}, "save", "draft"),
        (
            {"summary": "Build passed, no reusable lesson."},
            {"reusable": False},
            "journal-only",
            None,
        ),
        ({}, {"reusable": False, "meaningful": False}, "skip", None),
        ({"scope": "work"}, {}, "deny", None),
        ({}, {"material": "corporate"}, "deny", None),
        ({}, {"material": "customer"}, "deny", None),
        ({}, {"material": "unknown"}, "deny", None),
        ({"body": "password=synthetic-secret"}, {}, "deny", None),
        (
            {"extra": "Authorization: Bearer synthetic"},
            {"reusable": False, "meaningful": False},
            "deny",
            None,
        ),
        ({"tags": ["api_key=synthetic"]}, {"reusable": False}, "deny", None),
        ({"scope": "work", "type": "preference"}, {}, "deny", None),
        ({"id": "../escape"}, {}, "deny", None),
        ({"evidence": []}, {}, "deny", None),
        ({"status": ["verified"]}, {}, "deny", None),
        ({}, {"reusable": 1}, "deny", None),
        ({}, {"extra": True}, "deny", None),
    ],
)
def test_quality_policy_table(brain, changes, signals, decision, status):
    candidate = event(**changes)
    supplied = assessment()
    supplied.update(signals)
    before = copy.deepcopy(candidate)
    result = classify_capture(brain, candidate, supplied)
    assert result["decision"] == decision
    assert candidate == before
    assert not brain.ledger_path.exists()
    assert list(brain.vault.rglob("*.md")) == []
    if decision in {"deny", "skip"}:
        assert set(result) == {"decision", "reason"}
    else:
        prepared = result["candidate"]
        if status:
            assert prepared["status"] == status
            assert bool(result["warnings"]) == (status == "unverified")
        else:
            assert set(prepared) == {
                "scope",
                "mode",
                "event_id",
                "title",
                "source_agent",
                "summary",
            }
        assert brain.capture(prepared)["status"] == "saved"
        assert brain.capture(prepared)["status"] == "duplicate"


def test_preview_exact_update_and_pause_preserves_state(brain):
    brain.capture(event(project="one", tags=["python"]))
    original = brain.read("git-version")
    ledger = brain.ledger_path.read_bytes()
    result = classify_capture(
        brain, event(event_id="updated", body="Corrected observation"), assessment()
    )
    assert result["decision"] == "update"
    assert brain.read("git-version") == original
    assert brain.ledger_path.read_bytes() == ledger
    brain.pause(True)
    assert classify_capture(brain, event(), assessment()) == {
        "decision": "skip",
        "reason": "paused",
    }
    assert (
        classify_capture(brain, event(body="password=synthetic"), assessment())["decision"]
        == "deny"
    )
    brain.pause(False)
    assert brain.capture(result["candidate"])["status"] == "saved"
    assert "project: one" in brain.read("git-version")
    assert "- python" in brain.read("git-version")


def test_preview_deduplication_and_conflicts(brain):
    candidate = event()
    brain.capture(candidate)
    assert classify_capture(brain, candidate, assessment()) == {
        "decision": "skip",
        "reason": "duplicate-event",
    }
    assert classify_capture(brain, event(body="Different fact"), assessment()) == {
        "decision": "deny",
        "reason": "event-id-payload-conflict",
    }
    ledger = brain.ledger()
    ledger["events"][candidate["event_id"]]["status"] = "pending"
    brain.ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    result = classify_capture(brain, candidate, assessment())
    assert result["decision"] == "update" and result["warnings"] == ["pending-event-retry"]
    assert brain.status()["pending"] == 1


def test_journal_missing_summary_and_invalid_assessments(brain):
    for supplied in [None, {}, [], dict(assessment(), material="fiction")]:
        assert classify_capture(brain, event(), supplied)["decision"] == "deny"
    assert (
        classify_capture(brain, event(), dict(assessment(), reusable=False))["decision"] == "deny"
    )
    journal = {
        "scope": "personal",
        "mode": "journal-only",
        "event_id": "progress",
        "title": "Build complete",
        "source_agent": "codex",
        "summary": "Synthetic build passed",
    }
    assert classify_capture(brain, journal, assessment())["decision"] == "journal-only"


def test_fresh_stdio_and_cli_preview_match_without_writes(brain, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(dict(brain.config, schema_version=1)), encoding="utf-8")
    request = {"candidate": event(), "assessment": dict(assessment(), evidence_kind="none")}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")

    async def scenario():
        transport = {
            "mcpServers": {
                "brain": {
                    "command": sys.executable,
                    "args": ["-m", "second_brain.cli", "--config", str(config), "serve"],
                    "env": {
                        "FASTMCP_CHECK_FOR_UPDATES": "off",
                        "FASTMCP_SHOW_SERVER_BANNER": "false",
                    },
                }
            }
        }
        async with Client(transport) as client:
            assert "classify_memory" in {t.name for t in await client.list_tools()}
            result = await client.call_tool("classify_memory", request)
            assert result.data["candidate"]["status"] == "unverified"
            return result.data

    expected = asyncio.run(scenario())
    output = subprocess.run(
        [
            sys.executable,
            "-m",
            "second_brain.cli",
            "--config",
            str(config),
            "classify",
            "--request-file",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert output.returncode == 0, output.stderr
    assert json.loads(output.stdout) == expected
    assert not brain.ledger_path.exists()
    assert list(brain.vault.rglob("*.md")) == []
