import asyncio
import json
import os
import subprocess
import sys

import pytest
from fastmcp import Client

from second_brain.catalog import normalized, search_excerpt
from second_brain.core import Brain
from second_brain.journal import read_journal
from second_brain.server import create_server
from second_brain.viewer import Viewer, preview_text
from second_brain.workflow import timeline, overview


@pytest.fixture(params=["personal", "work"])
def brain(tmp_path, request):
    return Brain(
        dict(
            scope=request.param,
            timezone="Europe/Madrid",
            vault_path=str(tmp_path / "vault"),
            state_path=str(tmp_path / "state"),
        )
    )


def test_match_context_has_deep_command_and_unicode_without_html(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    content = (
        "# Guía\n\n"
        + "Texto anterior. " * 100
        + "\n\n```sh\necho comprobación\n```\n\nIP: 192.0.2.10\n"
    )
    (docs / "guide.md").write_text(content, encoding="utf-8")
    brain = Brain(
        dict(
            scope="personal",
            timezone="Europe/Madrid",
            vault_path=str(tmp_path / "vault"),
            state_path=str(tmp_path / "state"),
            documentation_roots={"demo": str(docs)},
        )
    )
    result = Viewer(brain).items({"q": ["COMPROBACION"]})
    assert result["total"] == 1 and "echo comprobación" in result["items"][0]["preview"]
    assert "192.0.2.10" in preview_text(content, "Guía", "192.0.2.10")
    assert "comprobación" in search_excerpt("😀 " * 200 + "comprobación final", "comprobacion")
    assert normalized("Straße café") == "strasse cafe"
    (docs / "formatted.md").write_text("# Otro\n\nCo**man**do formateado.\n", encoding="utf-8")
    assert Viewer(brain).items({"q": ["comando formateado"]})["total"] == 1


def test_journal_search_filters_before_pages_and_preserves_task_board(brain, tmp_path):
    base = dict(scope=brain.scope, mode="journal-only", source_agent="manual", project="demo")
    brain.capture(
        dict(
            base,
            event_id="needle",
            title="Resultado útil",
            summary="Comprobación de conexión 192.0.2.10",
            tasks=[dict(id="review", title="Revisar prueba", details="", status="open", version=0)],
        )
    )
    for index in range(24):
        brain.capture(
            dict(
                base,
                event_id="other-" + str(index),
                title="Otra actividad",
                summary="Sin coincidencias",
            )
        )
    found = timeline(brain, query="COMPROBACION 192.0.2.10")
    assert found["total"] == 1 and found["items"][0]["event_id"] == "needle"
    assert "192.0.2.10" in found["items"][0]["match_context"]
    assert timeline(brain, query="missing")["total"] == 0
    assert timeline(brain, project="different", query="conexión")["total"] == 0
    assert overview(brain)["active_total"] == 1
    expected = read_journal(brain, query="COMPROBACION 192.0.2.10")
    assert expected["total"] == 1 and expected["items"][0]["event_id"] == "needle"
    with pytest.raises(ValueError):
        read_journal(brain, view="tasks", project="demo", query="anything")
    with pytest.raises(ValueError):
        timeline(brain, query="x" * 301)

    async def protocol():
        async with Client(create_server(brain.config)) as client:
            assert (
                await client.call_tool("read_journal", {"query": "COMPROBACION 192.0.2.10"})
            ).data == expected

    asyncio.run(protocol())
    config = tmp_path / "config.json"
    config.write_text(json.dumps({**brain.config, "schema_version": 1}), encoding="utf-8")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "second_brain.cli",
            "--config",
            str(config),
            "journal",
            "--query",
            "COMPROBACION 192.0.2.10",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=os.environ.copy(),
        timeout=15,
    )
    assert run.returncode == 0 and json.loads(run.stdout) == expected


def test_agent_log_context_reports_match_outside_initial_preview(brain):
    from second_brain.agent_log import AgentLog
    from test_agent_log import action

    store = AgentLog(brain)
    store.configure(True, 0)
    store.record(
        {
            **action(scope=brain.scope),
            "context": "Contexto anterior. " * 30 + "coincidencia-profunda",
        }
    )
    result = store.query("coincidencia-profunda", max_chars=4000)
    assert result["total"] == 1
    assert "coincidencia-profunda" in result["items"][0]["match_context"]
    assert len(json.dumps(result, ensure_ascii=False)) <= 4000
