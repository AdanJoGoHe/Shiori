import asyncio
import hashlib
import io
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastmcp import Client

from second_brain.cli import MANAGED_COMMANDS, create_parser
from second_brain.core import Brain
from second_brain.intake import note_flow, read_json
from second_brain.quality import classify_capture
from second_brain.server import create_server
from test_core import event
from test_runtime import managed as managed


@pytest.fixture(params=["personal", "work"])
def deployment(tmp_path, request):
    config = dict(
        schema_version=1,
        scope=request.param,
        timezone="Europe/Madrid",
        vault_path=str(tmp_path / "vault"),
        state_path=str(tmp_path / "state"),
    )
    brain = Brain(config)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return brain, path


def request_for(brain, **changes):
    return {
        "candidate": event(scope=brain.scope, **changes),
        "assessment": dict(
            material="personal" if brain.scope == "personal" else "corporate",
            meaningful=True,
            reusable=True,
            evidence_kind="observed",
        ),
    }


def cli(path, *arguments, payload=None):
    return subprocess.run(
        [sys.executable, "-m", "second_brain.cli", "--config", str(path), *arguments],
        input=None
        if payload is None
        else payload
        if isinstance(payload, bytes)
        else json.dumps(payload, ensure_ascii=False).encode(),
        capture_output=True,
        timeout=20,
    )


def test_exact_id_text_read_and_tag_only_cli(deployment):
    brain, path = deployment
    candidate = request_for(
        brain, body="kubernetes\nComprobación ágil 😀", tags=["kubernetes", "windows"]
    )["candidate"]
    brain.capture(candidate)
    brain.capture(
        dict(candidate, id="git-version-other", event_id="other", tags=["kubernetes-prod"])
    )
    brain.capture(dict(candidate, id="untagged", event_id="third", tags=[]))
    exact = json.loads(cli(path, "search", "--id", "git-version").stdout)
    assert exact["found"] and [row["id"] for row in exact["notes"]] == ["git-version"]
    missing = json.loads(cli(path, "search", "--id", "missing").stdout)
    assert missing == {"found": False, "id": "missing", "notes": []}
    assert cli(path, "search", "--id", "git-version", "kubernetes").returncode != 0
    assert cli(path, "search", "--id", "../outside").returncode != 0
    found = json.loads(cli(path, "search", "--tag", " KUBERNETES ", "--tag", "windows").stdout)
    assert [row["id"] for row in found] == ["git-version"]
    assert json.loads(cli(path, "search", "--tag", "missing").stdout) == []
    text = cli(path, "read", "git-version", "--format", "text")
    assert text.returncode == 0 and text.stdout.decode() == brain.read("git-version")
    assert json.loads(cli(path, "read", "git-version").stdout) == text.stdout.decode()
    absent = cli(path, "read", "missing", "--format", "text")
    assert absent.returncode != 0 and not absent.stdout
    # A corrupt registered note is an error, not found=false.
    brain.path(brain.ledger()["notes"]["git-version"]).unlink()
    assert cli(path, "search", "--id", "git-version").returncode != 0


def test_stdin_note_preview_apply_diff_and_original_file(deployment, tmp_path):
    brain, path = deployment
    request = request_for(
        brain, body="Primera línea 😀\nSegunda línea", tags=["windows"], project="demo"
    )
    source = tmp_path / "request.json"
    original = json.dumps(request, ensure_ascii=False).encode("utf-8-sig")
    source.write_bytes(original)
    preview = cli(path, "note", "--request-file", str(source))
    prepared = json.loads(preview.stdout)
    assert preview.returncode == 0 and prepared["decision"] == "save" and not prepared["applied"]
    assert not brain.ledger_path.exists() and not list(brain.vault.rglob("*.md"))
    saved = cli(
        path,
        "note",
        "--request-file",
        "-",
        "--apply",
        "--expect-revision",
        "absent",
        payload=request,
    )
    assert saved.returncode == 0 and json.loads(saved.stdout)["capture"]["status"] == "saved"
    assert source.read_bytes() == original
    assert (
        json.loads(cli(path, "note", "--request-file", "-", "--apply", payload=request).stdout)[
            "reason"
        ]
        == "duplicate-event"
    )
    update = request_for(brain, event_id="update", body="Primera línea 😀\nPárrafo añadido")
    diff = json.loads(cli(path, "classify", "--request-file", "-", payload=update).stdout)
    assert diff["decision"] == "update" and "+Párrafo añadido" in diff["diff"]["text"]
    assert "updated_at" not in diff["diff"]["text"] and "- windows" not in diff["diff"]["text"]
    stale = cli(
        path,
        "note",
        "--request-file",
        "-",
        "--apply",
        "--expect-revision",
        "absent",
        payload=update,
    )
    assert (
        stale.returncode == 1
        and json.loads(stale.stdout)["capture"]["reason"] == "note-revision-changed"
    )
    revision = diff["diff"]["base_revision"]
    applied = cli(
        path,
        "note",
        "--request-file",
        "-",
        "--apply",
        "--expect-revision",
        revision,
        payload=update,
    )
    assert applied.returncode == 0 and json.loads(applied.stdout)["applied"]
    assert "- windows" in brain.read("git-version") and "project: demo" in brain.read("git-version")


@pytest.mark.parametrize(
    "payload",
    [b"", b"{", b"\xff", b" " * 40001, b"[]", b'{"candidate":{}}'],
    ids=["empty", "truncated", "encoding", "oversize", "array", "wrapper"],
)
def test_invalid_stdin_request_does_not_write(deployment, payload):
    brain, path = deployment
    result = cli(path, "classify", "--request-file", "-", payload=payload)
    assert result.returncode == 1 and not result.stdout and not brain.ledger_path.exists()


def test_stdin_capture_requires_candidate_not_classification_wrapper(deployment):
    brain, path = deployment
    request = request_for(brain)
    assert cli(path, "capture", "--event-file", "-", payload=request).returncode == 1
    prepared = json.loads(cli(path, "classify", "--request-file", "-", payload=request).stdout)[
        "candidate"
    ]
    assert (
        json.loads(cli(path, "capture", "--event-file", "-", payload=prepared).stdout)["status"]
        == "saved"
    )
    assert (
        json.loads(cli(path, "capture", "--event-file", "-", payload=prepared).stdout)["status"]
        == "duplicate"
    )
    assert (
        cli(path, "capture", "--event-file", "-", payload=dict(prepared, body="Changed")).returncode
        == 1
    )


def test_note_journal_deny_pause_and_pending_retry(deployment, monkeypatch):
    brain, _ = deployment
    import second_brain.core as core

    request = request_for(brain)
    denied = dict(request, assessment=dict(request["assessment"], material="unknown"))
    assert note_flow(brain, denied, apply=True) == {
        "decision": "deny",
        "reason": "non-personal-or-unknown-material"
        if brain.scope == "personal"
        else "non-corporate-or-unknown-material",
        "applied": False,
    }
    journal = request_for(brain, summary="Synthetic build passed")
    journal["assessment"]["reusable"] = False
    assert note_flow(brain, journal, apply=True)["capture"]["status"] == "saved"
    assert not brain.ledger()["notes"]
    brain.pause(True)
    assert note_flow(brain, request, apply=True)["reason"] == "paused"
    brain.pause(False)
    request["candidate"]["event_id"] = "note-retry"
    writer = core.atomic_write

    def interrupted(path, content):
        if "journal" in path.parts:
            raise OSError("Synthetic interruption")
        writer(path, content)

    monkeypatch.setattr(core, "atomic_write", interrupted)
    with pytest.raises(OSError):
        note_flow(brain, request, apply=True)
    assert brain.status()["pending"] == 1
    monkeypatch.setattr(core, "atomic_write", writer)
    result = note_flow(brain, request, apply=True, expect_revision="absent")
    assert result["capture"]["status"] == "saved" and brain.status()["pending"] == 0


def test_diff_normalization_bounds_and_concurrent_note_writes(deployment):
    brain, _ = deployment
    request = request_for(brain, body="old\n" * 3000, tags=["windows"])
    brain.capture(request["candidate"])
    same = classify_capture(
        brain, dict(request["candidate"], event_id="same"), request["assessment"]
    )
    assert same["diff"]["unchanged"]
    change = request_for(brain, event_id="change", body="new\n" * 3000)
    preview = note_flow(brain, change)
    assert preview["diff"]["truncated"] and len(preview["diff"]["text"]) <= 12000
    revision = hashlib.sha256(brain.read("git-version").encode()).hexdigest()

    def apply(index):
        return note_flow(
            brain,
            request_for(brain, event_id=f"writer-{index}", body=f"Changed {index}"),
            apply=True,
            expect_revision=revision,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, range(2)))
    assert sorted(row["capture"]["status"] for row in results) == ["blocked", "saved"]


def test_interactive_stdin_refuses_to_wait(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    with pytest.raises(ValueError, match="interactive wait"):
        read_json("-")


def test_managed_help_and_errors_without_touching_a_store(tmp_path, capsys):
    from second_brain.runtime import run

    root = tmp_path / "absent"
    assert run(root, ["--help"]) == 0
    help_text = capsys.readouterr().out
    assert "note" in help_text and "--config" not in help_text and "install-codex" not in help_text
    parser = create_parser(managed=True)
    commands = next(action for action in parser._actions if getattr(action, "choices", None))
    assert set(commands.choices) == set(MANAGED_COMMANDS)
    for arguments in [[], ["sarch"]]:
        with pytest.raises(ValueError):
            run(root, arguments)
        assert "note" in capsys.readouterr().err
    assert not root.exists()


def test_mcp_exact_tags_diff_and_no_provider(deployment, monkeypatch):
    brain, _ = deployment
    brain.capture(request_for(brain, tags=["kubernetes"])["candidate"])
    brain.capture(
        request_for(brain, id="other", event_id="other", tags=["kubernetes-prod"])["candidate"]
    )

    async def unavailable(*args):
        raise AssertionError("Canonical requests must not start the provider")

    monkeypatch.setattr("second_brain.server.provider_search", unavailable)

    async def scenario():
        async with Client(create_server(brain.config)) as client:
            exact = await client.call_tool("search_memory", {"note_id": "git-version"})
            assert exact.data["found"] and exact.data["ranking"] == "exact-id"
            missing = await client.call_tool("search_memory", {"note_id": "absent"})
            assert not missing.data["found"]
            found = await client.call_tool("search_memory", {"filters": {"tags": ["kubernetes"]}})
            assert [row["id"] for row in found.data["notes"]] == ["git-version"]
            result = await client.call_tool(
                "classify_memory", request_for(brain, event_id="mcp-update", body="New paragraph")
            )
            assert "+New paragraph" in result.data["diff"]["text"]

    asyncio.run(scenario())


def test_mcp_startup_failure_guides_to_same_cli(deployment, monkeypatch, capsys):
    from second_brain.cli import main

    brain, path = deployment
    monkeypatch.setattr(sys, "argv", ["shiori", "--config", str(path), "serve"])

    def failed(*args):
        raise RuntimeError("SYNTHETIC-PRIVATE-DETAIL")

    monkeypatch.setattr("second_brain.server.serve", failed)
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 1
    captured = capsys.readouterr()
    assert not captured.out and "SYNTHETIC-PRIVATE-DETAIL" not in captured.err
    assert (
        str(path) in captured.err
        and "pending" in captured.err
        and "same deployment" in captured.err
    )


def test_note_applies_the_classified_candidate(deployment):
    brain, path = deployment
    request = request_for(brain)
    request["assessment"]["evidence_kind"] = "none"
    result = json.loads(cli(path, "note", "--request-file", "-", "--apply", payload=request).stdout)
    assert result["candidate"]["status"] == "unverified"
    assert "status: unverified" in brain.read("git-version")


@pytest.mark.parametrize("failure", ["exit", "unavailable", "timeout"])
def test_managed_mcp_diagnostics_keep_protocol_stdout_clean(managed, monkeypatch, capsys, failure):
    from second_brain import runtime

    root, _, _ = managed
    monkeypatch.setattr(runtime, "installed_version", lambda _: "1.2.3a4")

    def stopped(*args, **kwargs):
        if failure == "unavailable":
            raise FileNotFoundError("Synthetic interpreter unavailable")
        if failure == "timeout":
            raise subprocess.TimeoutExpired("synthetic-transport", 1)
        return 1

    monkeypatch.setattr(runtime.subprocess, "call", stopped)
    monkeypatch.setattr(sys, "argv", ["shiori-runtime", "--root", str(root), "run", "serve"])
    with pytest.raises(SystemExit) as result:
        runtime.main()
    assert result.value.code == 1
    captured = capsys.readouterr()
    assert not captured.out and "shiori.cmd" in captured.err and "pending" in captured.err
    assert "same deployment" in captured.err


def test_fallback_managed_context_cannot_select_a_different_profile(tmp_path, monkeypatch):
    from second_brain.diagnostics import mcp_fallback

    root = tmp_path / "work"
    monkeypatch.setenv("SHIORI_MANAGED_ROOT", str(root))
    assert "shiori.cmd" in mcp_fallback(config=root / "data/config.json")
    personal = mcp_fallback(config=tmp_path / "personal.json")
    assert "shiori.cmd" not in personal and "personal.json" in personal
