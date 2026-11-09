"""Favorites UI, MCP and CLI against disposable fixtures in both scopes."""

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
from second_brain.viewer import ViewerServer


def main():
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Node and Playwright are required")
    screenshots = Path(tempfile.mkdtemp(prefix="shiori-favorites-screens-"))
    reports = []
    with tempfile.TemporaryDirectory(prefix="shiori-favorites-browser-") as folder:
        root = Path(folder)
        for scope in ["personal", "work"]:
            docs = root / scope / "docs"
            docs.mkdir(parents=True)
            guide = docs / "guide.md"
            guide.write_text(
                "# Guía del laboratorio\n\nUsa `echo ejemplo` para comprobar la instalación.\n",
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
            log = AgentLog(brain)
            log.configure(True, 0)
            log.record(
                dict(
                    schema_version=1,
                    scope=scope,
                    event_id="example-link",
                    agent="manual",
                    session="demo-session",
                    project="demo",
                    occurred_at=None,
                    kind="link-found",
                    outcome="unknown",
                    summary="Enlace del laboratorio",
                    command=None,
                    context="Referencia ficticia sin descargar",
                    references=[
                        dict(
                            kind="url",
                            target="https://example.test/log-guide",
                            label="Guía del Agent log",
                        )
                    ],
                    corrects=None,
                    correction_reason="",
                    coverage="reported",
                )
            )
            log.configure(False, log.status()["revision"])
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
                                guide=str(guide),
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
                finally:
                    server.shutdown()
                    thread.join(5)
            expected = Favorites(brain).query("echo")
            assert expected["total"] == 1

            async def protocol():
                async with Client(create_server(config)) as client:
                    assert len(await client.list_tools()) == 18
                    assert (
                        await client.call_tool("read_favorites", {"query": "echo"})
                    ).data == expected

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
                    "favorites",
                    "list",
                    "echo",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
            )
            assert run.returncode == 0 and json.loads(run.stdout) == expected
            # A new port and capability, with no browser storage, must see the same records.
            with ViewerServer(Brain(config)) as restarted:
                thread = threading.Thread(target=restarted.serve_forever, daemon=True)
                thread.start()
                try:
                    from urllib.request import urlopen

                    assert (
                        json.load(urlopen(restarted.url + "api/favorites?query=echo")) == expected
                    )
                finally:
                    restarted.shutdown()
                    thread.join(5)
    print(
        json.dumps(
            dict(
                status="passed",
                data="synthetic-only",
                reports=reports,
                installed_protocol_cli_restart="passed",
                screenshots=str(screenshots),
            )
        )
    )


if __name__ == "__main__":
    main()
