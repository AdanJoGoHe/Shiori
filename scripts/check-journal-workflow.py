"""Browser acceptance against a disposable synthetic diary; never a configured deployment."""

import json
import argparse
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from second_brain.core import Brain
from second_brain.viewer import ViewerServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-script", type=Path)
    parser.add_argument("--scope", choices=["personal", "work"], default="personal")
    args = parser.parse_args()
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Node and Playwright are required for this optional check")
    with tempfile.TemporaryDirectory(prefix="shiori-journal-browser-") as folder:
        root = Path(folder).resolve()
        brain = Brain(
            dict(
                scope=args.scope,
                timezone="Europe/Madrid",
                vault_path=str(root / "vault"),
                state_path=str(root / "state"),
            )
        )
        now = datetime(2026, 11, 3, 12, tzinfo=ZoneInfo("Europe/Madrid"))
        brain.now = lambda: now - timedelta(days=1)
        base = dict(
            scope=args.scope,
            mode="journal-only",
            source_agent="manual",
            project="diario-demo",
            activity="lector-utf8",
        )
        task = dict(
            id="editor",
            title="Validar el lector en el editor",
            status="open",
            details="Usar el documento de prueba",
            version=0,
        )
        brain.capture(
            dict(
                base,
                event_id="lector-inicio",
                title="Lectura UTF-8 preparada",
                summary="Preparado el ejemplo de lectura.",
                tasks=[task],
                progress={"completed": ["Añadido el lector de ejemplo."]},
            )
        )
        brain.now = lambda: now
        brain.capture(
            dict(
                base,
                mode="note",
                id="lector-demo",
                type="knowledge",
                status="unverified",
                body="Nota ficticia enlazada con el diario.",
                evidence="Ejemplo sintético, no comprobación independiente.",
                event_id="lector-final",
                title="Lectura UTF-8 comprobada",
                summary="El lector conserva los acentos y los saltos de línea.",
                tasks=[dict(task, status="blocked", version=1)],
                progress={
                    "completed": ["Corregida la lectura de caracteres."],
                    "checks": ["Tres pruebas locales pasaron."],
                    "decisions": ["Conservar el formato Markdown."],
                    "blockers": ["Falta comprobar el editor."],
                    "next_steps": ["Abrir un ejemplo sintético en el editor."],
                },
            )
        )
        brain.capture(
            dict(
                base,
                activity="paquete",
                event_id="paquete",
                title="Paquete preparado",
                summary="Preparados los archivos de instalación.",
                tasks=[
                    dict(task, id="paquete", title="Revisar el paquete", status="open", version=0),
                    dict(
                        task, id="documentacion", title="Escribir la guía", status="done", version=0
                    ),
                ],
            )
        )
        brain.capture(
            dict(
                base,
                project="otro-demo",
                event_id="otro",
                title="Otro proyecto",
                summary="Avance de un proyecto distinto.",
            )
        )
        # The archive is not a rolling 31-day store; old months stay queryable.
        brain.now = lambda: now.replace(month=5, day=12)
        brain.capture(
            dict(
                base,
                event_id="historical-may",
                title="Trabajo de mayo",
                summary="Resultado ficticio guardado hace varios meses.",
            )
        )
        brain.now = lambda: now
        originals = {path: path.read_bytes() for path in brain.vault.rglob("*.md")}
        screenshots = Path(tempfile.mkdtemp(prefix="shiori-journal-screens-"))
        with ViewerServer(brain) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(
                    [node, str(Path(__file__).with_suffix(".cjs"))],
                    input=json.dumps(
                        {"url": server.url, "screenshots": str(screenshots), "scope": args.scope}
                    ),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=100,
                )
                if result.returncode:
                    raise AssertionError(result.stderr.replace(server.url, "<synthetic-viewer>/"))
                report = json.loads(result.stdout)
                if args.inspect_script:
                    inspection = subprocess.run(
                        [
                            node,
                            str(args.inspect_script),
                            server.url + "#diario",
                            "--app",
                            "--out",
                            str(screenshots / "inspection"),
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=90,
                    )
                    report["inspection_exit_code"] = inspection.returncode
                    report["inspection_error"] = inspection.stderr.replace(
                        server.url, "<synthetic-viewer>/"
                    )[:2000]
                    report["inspection_report"] = str(screenshots / "inspection")
                    print(inspection.stdout.replace(server.url, "<synthetic-viewer>/"))
                assert all(
                    path.read_bytes().startswith(content) for path, content in originals.items()
                )
                print(json.dumps(report))
            finally:
                server.shutdown()
                thread.join(5)


if __name__ == "__main__":
    main()
