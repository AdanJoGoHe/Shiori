"""Search scopes and reader acceptance using disposable synthetic profiles only."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from fastmcp import Client

from second_brain.agent_log import AgentLog
from second_brain.core import Brain
from second_brain.favorites import Favorites
from second_brain.server import create_server
from second_brain.viewer import Viewer, ViewerServer


def main():
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Node and Playwright are required")
    screenshots = Path(tempfile.mkdtemp(prefix="shiori-search-reader-screens-"))
    reports = []
    with tempfile.TemporaryDirectory(prefix="shiori-search-reader-") as folder:
        root = Path(folder)
        command = 'kubectl --context demo get pods\n  echo "listo 😀"'
        for scope in ["personal", "work"]:
            docs = root / scope / "docs"
            docs.mkdir(parents=True)
            guide = docs / "guide.md"
            guide.write_text(
                "---\nproject: demo\ntags: [network]\n---\n# Guía de recuperación\n\n"
                "Café del laboratorio y otro **Ca**fé.\n\n"
                + "\n\n".join(
                    "Párrafo ficticio para comprobar lectura larga y posición." for _ in range(45)
                )
                + "\n\n## Comandos\n\n```sh\n"
                + command
                + "\n"
                + "echo "
                + "x" * 240
                + "\n```\n\n"
                + "IP de documentación: 192.0.2.10. Ruta: /srv/laboratorio/config.\n\n"
                + "| Campo | Texto ancho |\n| --- | --- |\n| Demo | "
                + "valor" * 80
                + " |\n\n"
                + "<script>window.untrustedExecuted = true</script>\n",
                encoding="utf-8",
            )
            config = dict(
                schema_version=1,
                scope=scope,
                timezone="Europe/Madrid",
                vault_path=str(root / scope / "vault"),
                state_path=str(root / scope / "state"),
                documentation_roots={"demo": str(docs)},
            )
            brain = Brain(config)
            brain.capture(
                dict(
                    scope=scope,
                    id="demo-note",
                    event_id="demo-note",
                    title="Nota verificada de ejemplo",
                    type="knowledge",
                    status="verified",
                    source_agent="manual",
                    body="Comprobación ficticia.",
                    evidence="Fixture observado; no describe el equipo real.",
                    summary="Nota sintética",
                )
            )
            base = dict(scope=scope, mode="journal-only", source_agent="manual", project="demo")
            brain.capture(
                dict(
                    base,
                    event_id="needle",
                    title="Conexión del laboratorio",
                    summary="Comprobado 192.0.2.10",
                    tasks=[
                        dict(
                            id="review",
                            title="Revisar seguimiento",
                            details="Fixture",
                            status="open",
                            version=0,
                        )
                    ],
                )
            )
            for index in range(25):
                brain.capture(
                    dict(
                        base,
                        event_id="bulk-" + str(index),
                        title="Avance del ejemplo " + str(index),
                        summary="Preparación del laboratorio",
                    )
                )
            viewer = Viewer(brain)
            content = viewer.content("documentation:demo:guide.md")
            start = content["text"].index(command)
            mark = viewer.annotations.save(
                content,
                dict(
                    document_id=content["item"]["id"],
                    revision=content["revision"],
                    start=start,
                    end=start + len(command),
                    quote=command,
                    color="green",
                    tags=["comando"],
                    title="Comando del laboratorio",
                ),
            )
            Favorites(brain).save(
                dict(
                    target=content["item"]["id"],
                    title="Guía guardada",
                    project="demo",
                    tags=["network"],
                    version=0,
                )
            )
            log = AgentLog(brain)
            log.configure(True, 0)
            log.record(
                dict(
                    schema_version=1,
                    scope=scope,
                    event_id="demo-check",
                    agent="manual",
                    session="demo-session",
                    project="demo",
                    occurred_at=None,
                    kind="check",
                    outcome="success",
                    summary="Comprobación 192.0.2.10",
                    command="echo demo",
                    context="Fixture",
                    references=[],
                    corrects=None,
                    correction_reason="",
                    coverage="reported",
                )
            )
            originals = {
                p: p.read_bytes() for p in [guide, *brain.vault.rglob("*.md"), brain.ledger_path]
            }
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
                                mark=mark["id"],
                                screenshots=str(screenshots),
                            )
                        ),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=180,
                    )
                    if run.returncode:
                        raise AssertionError(run.stderr.replace(server.url, "<synthetic-viewer>/"))
                    reports.append(json.loads(run.stdout))
                finally:
                    server.shutdown()
                    thread.join(5)
            assert all(p.read_bytes() == raw for p, raw in originals.items())
            assert len(viewer.annotations.export()["items"]) == 2

            async def protocol():
                async with Client(create_server(config)) as client:
                    assert (await client.call_tool("read_journal", {"query": "192.0.2.10"})).data[
                        "total"
                    ] == 1

            asyncio.run(protocol())
            config_path = root / scope / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "second_brain.cli",
                    "--config",
                    str(config_path),
                    "journal",
                    "--query",
                    "192.0.2.10",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
            )
            assert run.returncode == 0 and json.loads(run.stdout)["total"] == 1
    print(
        json.dumps(
            dict(
                status="passed",
                data="synthetic-only",
                reports=reports,
                protocol_cli="passed",
                screenshots=str(screenshots),
            )
        )
    )


if __name__ == "__main__":
    main()
