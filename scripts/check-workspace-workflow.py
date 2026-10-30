"""Desktop workspace acceptance on disposable data, with no deployment configuration."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from second_brain.core import Brain
from second_brain.viewer import ViewerServer


def main():
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Node and Playwright are required for this optional check")
    screenshots = Path(tempfile.mkdtemp(prefix="shiori-workspace-screens-"))
    reports = []
    with tempfile.TemporaryDirectory(prefix="shiori-workspace-browser-") as folder:
        root = Path(folder)
        docs = root / "docs"
        docs.mkdir()
        command = 'kubectl get pods\nkubectl describe pod "demo"'
        prose = "Conservar evidencia antes de cambiar la configuración del ejemplo."
        (docs / "guide.md").write_text(
            "---\ntags: [kubernetes, demo]\nproject: laboratorio\n---\n"
            "# Comandos del laboratorio\n\n## Consultar\n\nContexto previo.\n\n"
            f"```sh\n{command}\n```\n\nContexto posterior.\n\n"
            f"## Recordatorio\n\n{prose}\n\nIP de documentación: `192.0.2.10`.\n",
            encoding="utf-8",
        )
        for index in range(24):
            (docs / f"page-{index:02}.md").write_text(
                f"# Página de ejemplo {index:02}\n\nContenido sintético.", encoding="utf-8"
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
            brain.now = lambda: datetime(2026, 10, 30, 23, 59, tzinfo=ZoneInfo("Europe/Madrid"))
            assert (
                brain.capture(
                    dict(
                        scope=scope,
                        mode="journal-only",
                        event_id="workspace-fixture",
                        source_agent="manual",
                        title="Lector comprobado",
                        summary="Comprobadas las marcas con un ejemplo ficticio.",
                    )
                )["status"]
                == "saved"
            )
            with ViewerServer(brain) as server:
                document = server.viewer.content("documentation:demo:guide.md")
                for quote, category in [
                    (command, "comando"),
                    (prose, "informacion-importante"),
                    ("192.0.2.10", "direccion-ip"),
                ]:
                    start = document["text"].index(quote)
                    server.viewer.annotations.save(
                        document,
                        dict(
                            document_id=document["item"]["id"],
                            revision=document["revision"],
                            start=start,
                            end=start + len(quote),
                            quote=quote,
                            color="green",
                            tags=[category],
                        ),
                    )
                before = {
                    path: path.read_bytes()
                    for base in [docs, brain.vault, brain.state]
                    for path in base.rglob("*")
                    if path.is_file()
                }
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    result = subprocess.run(
                        [node, str(Path(__file__).with_suffix(".cjs"))],
                        input=json.dumps(
                            dict(
                                url=server.url,
                                command=command,
                                scope=scope,
                                screenshots=str(screenshots),
                            )
                        ),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=120,
                    )
                    if result.returncode:
                        raise AssertionError(
                            result.stderr.replace(server.url, "<synthetic-viewer>/")
                        )
                    reports.append(json.loads(result.stdout))
                    assert all(path.read_bytes() == content for path, content in before.items())
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
