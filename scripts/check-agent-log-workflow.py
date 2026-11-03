"""Agent log acceptance on disposable personal/work fixtures, never an installed profile."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from second_brain.agent_log import AgentLog
from second_brain.core import Brain
from second_brain.viewer import ViewerServer


def main():
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Node and Playwright are required")
    reports = []
    screenshots = Path(tempfile.mkdtemp(prefix="shiori-agent-log-screens-"))
    with tempfile.TemporaryDirectory(prefix="shiori-agent-log-browser-") as folder:
        root = Path(folder)
        docs = root / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "# Guía de acciones\n\nDocumento ficticio enlazado desde el registro.\n",
            encoding="utf-8",
        )
        for scope in ["personal", "work"]:
            brain = Brain(
                dict(
                    scope=scope,
                    timezone="Europe/Madrid",
                    vault_path=str(root / scope / "vault"),
                    state_path=str(root / scope / "state"),
                    documentation_roots={"demo": str(docs)},
                )
            )
            brain.now = lambda: datetime(2026, 11, 3, 13, 30, tzinfo=ZoneInfo("Europe/Madrid"))
            brain.capture(
                dict(
                    scope=scope,
                    mode="journal-only",
                    event_id="agent-log-day",
                    source_agent="manual",
                    title="Avance del ejemplo",
                    summary="Se revisó el recorrido ficticio del diario.",
                    project="demo",
                )
            )
            log = AgentLog(brain)
            log.configure(True, 0)
            base = dict(
                schema_version=1,
                scope=scope,
                agent="manual",
                session="session-main",
                project="demo",
                occurred_at=None,
                kind="command-executed",
                outcome="success",
                summary="Acción de ejemplo",
                command="echo demo",
                context="Fixture sintético",
                references=[],
                corrects=None,
                correction_reason="",
                coverage="reported",
            )
            for index in range(24):
                log.record(
                    {
                        **base,
                        "event_id": f"bulk-{index}",
                        "session": "session-bulk",
                        "summary": f"Acción del ejemplo {index}",
                        "occurred_at": f"2026-11-03T12:{index:02}:00+01:00",
                    }
                )
            command = "kubectl get pods\nkubectl describe pod demo"
            log.record(
                {
                    **base,
                    "event_id": "command-demo",
                    "command": command,
                    "summary": "Consultar el ejemplo del laboratorio",
                    "occurred_at": "2026-11-03T13:01:00+01:00",
                    "references": [
                        dict(
                            kind="content",
                            target="documentation:demo:guide.md",
                            label="Guía del ejemplo",
                        ),
                        dict(
                            kind="journal-event", target="agent-log-day", label="Avance del diario"
                        ),
                        dict(
                            kind="url",
                            target="https://example.test/reference",
                            label="Referencia externa",
                        ),
                        dict(kind="file", target="examples/demo.txt", label="Archivo informado"),
                        dict(kind="content", target=f"note:{scope}:missing", label="Nota ausente"),
                    ],
                }
            )
            for kind, event_id in [("link-found", "found-demo"), ("page-visited", "visited-demo")]:
                log.record(
                    {
                        **base,
                        "event_id": event_id,
                        "kind": kind,
                        "outcome": "unknown",
                        "command": None,
                        "summary": "Referencia de una visita ficticia"
                        if kind == "page-visited"
                        else "Referencia encontrada en el ejemplo",
                        "references": [
                            dict(
                                kind="url",
                                target="https://example.test/reference",
                                label="Referencia externa",
                            )
                        ],
                    }
                )
            log.record(
                {
                    **base,
                    "event_id": "failed-demo",
                    "kind": "check",
                    "outcome": "failure",
                    "command": "python -m pytest tests/demo.py",
                    "summary": "Fallo ficticio de comprobación",
                }
            )
            log.record(
                {
                    **base,
                    "event_id": "timeout-demo",
                    "outcome": "unknown",
                    "summary": "Timeout ficticio; efectos desconocidos",
                    "command": "python demo.py",
                }
            )
            log.record(
                {
                    **base,
                    "event_id": "yesterday-demo",
                    "summary": "Acción informada ayer",
                    "occurred_at": "2026-11-02T23:59:00+01:00",
                }
            )
            log.record(
                {
                    **base,
                    "event_id": "correction-demo",
                    "corrects": "failed-demo",
                    "kind": "check",
                    "command": "python -m pytest tests/demo.py",
                    "outcome": "unknown",
                    "correction_reason": "El resultado del ejemplo no pudo confirmarse.",
                    "summary": "Resultado ficticio corregido",
                }
            )
            log.configure(False, log.status()["revision"])
            originals = {p: p.read_bytes() for p in brain.vault.rglob("*.md")}
            ledger = brain.ledger_path.read_bytes()
            with ViewerServer(brain) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    run = subprocess.run(
                        [node, str(Path(__file__).with_suffix(".cjs"))],
                        input=json.dumps(
                            dict(
                                url=server.url,
                                scope=scope,
                                command=command,
                                screenshots=str(screenshots),
                            )
                        ),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=150,
                    )
                    if run.returncode:
                        raise AssertionError(run.stderr.replace(server.url, "<synthetic-viewer>/"))
                    reports.append(json.loads(run.stdout))
                    assert all(p.read_bytes() == raw for p, raw in originals.items())
                    assert brain.ledger_path.read_bytes() == ledger
                finally:
                    server.shutdown()
                    thread.join(5)
    print(
        json.dumps(
            dict(
                status="passed",
                data="synthetic-only",
                reports=reports,
                screenshots=str(screenshots),
            )
        )
    )


if __name__ == "__main__":
    main()
