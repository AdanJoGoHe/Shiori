import asyncio
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastmcp import Client

from second_brain.agent_log import AgentLog, decode
from second_brain.annotations import Conflict
from second_brain.backup import backup, restore
from second_brain.core import Brain, load_config
from second_brain.server import create_server
from second_brain.viewer import ViewerServer
from test_core import brain as brain


def action(scope="personal", **changes):
    return dict(
        schema_version=1,
        scope=scope,
        event_id="example-action",
        agent="manual",
        session="session-demo",
        project="demo",
        occurred_at=None,
        kind="command-executed",
        outcome="success",
        summary="Comprobado el ejemplo",
        command='echo "demo"\necho "listo"',
        context="Fixture revisado, no material real",
        references=[],
        corrects=None,
        correction_reason="",
        coverage="reported",
        **changes,
    )


@pytest.mark.parametrize("scope", ["personal", "work"])
def test_activation_identity_retry_pause_and_corrections(tmp_path, scope):
    brain = Brain(
        dict(
            scope=scope,
            timezone="Europe/Madrid",
            vault_path=str(tmp_path / "vault"),
            state_path=str(tmp_path / "state"),
        )
    )
    log = AgentLog(brain)
    assert log.status()["enabled"] is False
    assert log.record(action(scope))["status"] == "blocked"
    assert not (brain.state / "agent-log.json").exists()
    log.configure(True, 0)
    event = action(scope)
    assert log.record(event)["status"] == "saved"
    before = (brain.state / "agent-log.json").read_bytes()
    assert log.record(event)["status"] == "duplicate"
    assert (brain.state / "agent-log.json").read_bytes() == before
    with pytest.raises(Conflict):
        log.record({**event, "summary": "Un resultado distinto"})
    correction = {
        **event,
        "event_id": "corrected-action",
        "corrects": event["event_id"],
        "outcome": "unknown",
        "correction_reason": "No se conservó el resultado de la comprobación",
    }
    log.record(correction)
    assert log.read(event["event_id"])["corrected_by"] == correction["event_id"]
    with pytest.raises(ValueError):
        log.record({**correction, "event_id": "fork"})
    brain.pause(True)
    assert log.record({**event, "event_id": "while-paused"})["status"] == "blocked"
    assert log.read(event["event_id"])["item"]["command"] == event["command"]
    log.configure(False, log.status()["revision"])
    assert log.record(event)["status"] == "duplicate"
    assert log.query()["total"] == 2
    assert brain.ledger()["notes"] == {} and brain.ledger()["events"] == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "work"},
        {"schema_version": True},
        {"coverage": "observed"},
        {"event_id": "../escape"},
        {"agent": "unknown"},
        {"occurred_at": "2026-11-03T01:00:00"},
        {"command": "password=synthetic-example-value"},
        {"command": "demo --password synthetic-example-value"},
        {"context": "https://user:pass@example.test/"},
        {"references": [{"kind": "file", "target": "https://example.test/", "label": "Fixture"}]},
        {"raw_output": "Unsupported output field"},
        {"context": "Authorization: Bearer synthetic-example-value"},
        {"kind": "command-proposed", "outcome": "success"},
        {"kind": "command-attempted", "outcome": "success"},
        {"references": [{"kind": "url", "target": "javascript:alert(1)", "label": "Fixture"}]},
        {
            "references": [
                {"kind": "url", "target": "https://user:pass@example.test/", "label": "Fixture"}
            ]
        },
        {
            "references": [
                {"kind": "url", "target": "https://example.test/?token=x", "label": "Fixture"}
            ]
        },
        {"references": [{"kind": "content", "target": "note:work:example", "label": "Fixture"}]},
        {
            "references": [
                {"kind": "content", "target": "documentation:demo:../../escape", "label": "Fixture"}
            ]
        },
        {"corrects": "missing", "correction_reason": "Fixture"},
    ],
)
def test_invalid_actions_never_change_existing_store(brain, changes):
    log = AgentLog(brain)
    log.configure(True, 0)
    before = (brain.state / "agent-log.json").read_bytes()
    with pytest.raises((ValueError, Conflict)):
        log.record({**action(), **changes})
    assert (brain.state / "agent-log.json").read_bytes() == before


def test_atomic_failure_concurrent_retry_and_corrupt_scope(brain, monkeypatch):
    import second_brain.agent_log as module

    log = AgentLog(brain)
    log.configure(True, 0)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: AgentLog(brain).record(action()), range(3)))
    assert [r["status"] for r in results].count("saved") == 1
    assert log.query()["total"] == 1
    before = (brain.state / "agent-log.json").read_bytes()
    original = module.atomic_write
    monkeypatch.setattr(
        module,
        "atomic_write",
        lambda *args: (_ for _ in ()).throw(OSError("Synthetic interruption")),
    )
    with pytest.raises(OSError):
        log.record({**action(), "event_id": "retry-event"})
    assert (brain.state / "agent-log.json").read_bytes() == before
    monkeypatch.setattr(module, "atomic_write", original)
    assert log.record({**action(), "event_id": "retry-event"})["status"] == "saved"
    data = log.export()
    data["scope"] = "work"
    (brain.state / "agent-log.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        log.query()
    with pytest.raises(ValueError):
        log.configure(False, data["revision"])


def test_historical_timezone_sort_filters_and_pagination(brain, monkeypatch):
    log = AgentLog(brain)
    log.configure(True, 0)
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-11-03T00:01:00+01:00"))
    original = {
        **action(),
        "event_id": "late-arrival",
        "occurred_at": "2026-05-12T22:30:00Z",
        "references": [dict(kind="journal-event", target="day-event", label="Avance")],
        "command": "echo archive",
    }
    log.record(original)
    result = log.query(
        "archive",
        {"start_date": "2026-05-13", "end_date": "2026-05-13", "journal_event": "day-event"},
    )
    assert result["total"] == 1 and result["items"][0]["day"] == "2026-05-13"
    assert log.query()["total"] == 0  # Arrival time does not replace known occurrence time.
    for index in range(23):
        log.record(
            {
                **action(),
                "event_id": f"more-{index}",
                "summary": "x" * 600,
                "command": "echo " + "y" * 1200,
            }
        )
    offset = 0
    ids = []
    while True:
        page = log.query(
            filters={"project": "demo", "session": "session-demo"}, offset=offset, max_chars=4000
        )
        assert len(json.dumps(page, ensure_ascii=False)) <= 4000
        ids.extend(i["event_id"] for i in page["items"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert len(set(ids)) == 23 and log.query(filters={"project": "other"})["total"] == 0
    assert log.read("late-arrival")["item"]["occurred_at"] == "2026-05-13T00:30:00+02:00"
    before = (brain.state / "agent-log.json").read_bytes()
    monkeypatch.setattr(brain, "now", lambda: datetime.fromisoformat("2026-11-04T00:01:00+01:00"))
    assert log.record(original)["status"] == "duplicate"
    assert (brain.state / "agent-log.json").read_bytes() == before


def test_store_limit_never_evicts_and_backup_restores_paused(brain, monkeypatch, tmp_path):
    import second_brain.agent_log as module

    log = AgentLog(brain)
    log.configure(True, 0)
    log.record(action())
    before = (brain.state / "agent-log.json").read_bytes()
    monkeypatch.setattr(module, "MAX_EVENTS", 1)
    with pytest.raises(ValueError):
        log.record({**action(), "event_id": "over-limit"})
    assert (brain.state / "agent-log.json").read_bytes() == before
    backup(brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    restored = Brain(load_config(tmp_path / "restored/config.json"))
    assert AgentLog(restored).export() == decode(before.decode())
    assert (
        AgentLog(restored).record({**action(), "event_id": "restored-action"})["status"]
        == "blocked"
    )


def test_session_opt_in_expires_and_keeps_history(brain, monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(brain, "now", lambda: now)
    log = AgentLog(brain)
    settings = ("session-demo", "manual", "demo", ["check", "page-visited"], 1)
    assert log.start_session(*settings)["status"] == "preview"
    path = brain.state / "agent-log.json"
    assert not path.exists()
    assert log.start_session(*settings, apply=True)["status"] == "enabled"
    assert AgentLog(Brain(brain.config)).status()["session_policy"]["id"] == "session-demo"
    with pytest.raises(Conflict):
        log.start_session(*settings, apply=True)
    with pytest.raises(Conflict):
        log.configure(True, log.status()["revision"])
    check = dict(action(), kind="check", command=None, context="")
    before = path.read_bytes()
    for fields in [
        {"session": "other"},
        {"agent": "codex"},
        {"project": None},
        {"kind": "command-executed", "command": "echo demo"},
    ]:
        assert log.record(dict(check, **fields))["reason"] == "agent-log-session-policy"
    for fields in [
        {"context": "Raw output excluded"},
        {"command": "echo demo"},
        {"references": [{"kind": "file", "target": "private/example.txt", "label": "Example"}]},
    ]:
        assert log.record(dict(check, **fields))["reason"] == "agent-log-session-needs-redaction"
    visit = dict(
        check,
        event_id="synthetic-visit",
        kind="page-visited",
        references=[{"kind": "url", "target": "https://example.test/path", "label": "Reference"}],
    )
    for suffix in ["?view=example", "#private-section", "?"]:
        ref = dict(visit["references"][0], target=f"https://example.test/path{suffix}")
        assert (
            log.record(dict(visit, references=[ref]))["reason"]
            == "agent-log-session-needs-redaction"
        )
    assert path.read_bytes() == before
    assert log.record(check)["status"] == log.record(visit)["status"] == "saved"
    assert log.query(filters={"session": "session-demo", "kind": "check"})["total"] == 1
    assert log.query(filters={"session": "unknown"})["total"] == 0
    backup(brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    recovered = Brain(load_config(tmp_path / "restored/config.json"))
    recovered.pause(False)
    assert AgentLog(recovered).status()["enabled"] is False
    assert "session_policy" not in AgentLog(recovered).status()
    assert AgentLog(recovered).read(visit["event_id"])["item"]["session"] == "session-demo"
    assert AgentLog(recovered).record(dict(check, event_id="new"))["status"] == "blocked"
    now += timedelta(minutes=1)
    assert log.status()["enabled"] is False
    assert log.record(dict(check, event_id="expired"))["reason"] == "agent-log-session-expired"
    assert log.record(check)["status"] == "duplicate"
    log.configure(False, log.status()["revision"])
    assert log.export()["schema_version"] == 1
    assert log.status()["total"] == 2 and "session_policy" not in log.status()


def test_http_origin_activation_and_safe_reference_resolution(brain):
    log = AgentLog(brain)
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def post(path, data, origin=server.origin):
            return urlopen(
                Request(
                    server.url + path,
                    data=json.dumps(data).encode(),
                    headers={"Content-Type": "application/json", "Origin": origin},
                    method="POST",
                )
            )

        try:
            with pytest.raises(HTTPError) as denied:
                post("api/agent-log/config", dict(enabled=True, revision=0), "https://example.test")
            assert denied.value.code == 403 and log.status()["enabled"] is False
            assert (
                json.load(post("api/agent-log/config", dict(enabled=True, revision=0)))["enabled"]
                is True
            )
            candidate = {
                **action(),
                "references": [
                    dict(kind="content", target="note:personal:missing", label="No disponible"),
                    dict(kind="file", target="examples/demo.txt", label="Ruta"),
                ],
            }
            assert json.load(post("api/agent-log", candidate))["status"] == "saved"
            result = json.load(urlopen(server.url + "api/agent-log?event_id=example-action"))
            assert result["item"]["command"] == candidate["command"]
            assert not any(r["available"] for r in result["references"])
            with pytest.raises(HTTPError) as stale:
                post("api/agent-log/config", dict(enabled=False, revision=1))
            assert stale.value.code == 409
            for suffix in [
                "api/agent-log?event_id=../escape",
                "api/agent-log?event_id=example-action&query=example",
                "api/agent-log?scope=work",
            ]:
                with pytest.raises(HTTPError):
                    urlopen(server.url + suffix)
        finally:
            server.shutdown()
            thread.join(5)


def test_mcp_and_configured_cli_parity_and_no_activation_by_agent(brain, tmp_path):
    async def scenario():
        async with Client(create_server(brain.config)) as client:
            assert len(await client.list_tools()) == 18
            assert not (await client.call_tool("memory_status", {})).data["agent_log"]["enabled"]
            assert (await client.call_tool("record_agent_action", {"candidate": action()})).data[
                "status"
            ] == "blocked"
            AgentLog(brain).configure(True, 0)
            assert (await client.call_tool("record_agent_action", {"candidate": action()})).data[
                "status"
            ] == "saved"
            assert (await client.call_tool("read_agent_log", {"event_id": "example-action"})).data[
                "item"
            ]["command"] == action()["command"]
            denied = await client.call_tool(
                "record_agent_action",
                {"candidate": {**action(), "command": "password=synthetic-private-value"}},
            )
            assert "synthetic-private-value" not in json.dumps(denied.data)
            assert (await client.call_tool("read_agent_log", {"query": "demo"})).data["total"] == 1

    asyncio.run(scenario())
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({**brain.config, "scope": brain.scope, "schema_version": 1}), encoding="utf-8"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "second_brain.cli",
            "--config",
            str(config),
            "agent-log",
            "record",
            "--event-file",
            "-",
        ],
        input=json.dumps(action()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )
    assert run.returncode == 0 and json.loads(run.stdout)["status"] == "duplicate"
    run = subprocess.run(
        [sys.executable, "-m", "second_brain.cli", "--config", str(config), "agent-log", "disable"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )
    assert json.loads(run.stdout)["status"] == "preview" and AgentLog(brain).status()["enabled"]


def test_runtime_rejects_candidate_missing_log_reader(tmp_path, monkeypatch):
    from second_brain import runtime

    root = tmp_path / "install"
    (root / "data/state").mkdir(parents=True)
    (root / "data/state/agent-log.json").write_text("{}")

    def candidate(args):
        assert "-c" in args and "agent_log" in args[args.index("-c") + 1]
        raise ValueError("Candidate has no log reader")

    monkeypatch.setattr(runtime, "command", candidate)
    with pytest.raises(ValueError, match="no log reader"):
        runtime.probe(root, "0.1.0a5")
