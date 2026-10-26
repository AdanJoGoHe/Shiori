"""Optional browser acceptance: owned synthetic processes/files only; no personal config."""

import json
import multiprocessing
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from second_brain.annotations import Annotations
from second_brain.core import Brain

PROSE = "Esta frase conserva una observación sintética."
COMMAND = 'git --version\necho "Listo 😀"'
CONTEXT = "Contexto sintético para distinguir esta sección de cualquier otra. " * 4
BODY = f"""---
project: acceptance
tags: [synthetic]
---
# SB-ANNOTATION-ACCEPTANCE

Datos sintéticos, sin información del propietario.

{PROSE}

{CONTEXT}

```powershell
{COMMAND}
```

{CONTEXT}

Servidor de ejemplo: `192.0.2.44`. Ruta de ejemplo: `C:\\fixture\\datos`.

Primera sección: texto repetido. Contexto uno.

Segunda sección: texto repetido. Contexto dos.

[Enlace local](other.md). <script>globalThis.fixtureExecuted = true</script>

Texto inerte: `<img src=x onerror="globalThis.fixtureExecuted=true">`.
"""


def serve(config, connection, stop):
    from second_brain.viewer import ViewerServer

    with ViewerServer(Brain(config), 0) as server:
        server.timeout = 0.2
        connection.send(server.url)
        connection.close()
        while not stop.is_set():
            server.handle_request()


def main():
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Set SB_TEST_NODE to Node; optional Playwright/browser must be installed")
    script = Path(__file__).with_name("check-annotation-workflow.cjs")
    with tempfile.TemporaryDirectory(prefix="sb-annotation-acceptance-") as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert root.name.startswith("sb-annotation-acceptance-")
        docs = root / "docs"
        docs.mkdir()
        source = docs / "guide.md"
        source.write_text(BODY, encoding="utf-8")
        (docs / "other.md").write_text("# Synthetic link destination", encoding="utf-8")
        config = {
            "scope": "personal",
            "timezone": "Europe/Madrid",
            "vault_path": str(root / "vault"),
            "state_path": str(root / "state"),
            "documentation_roots": {"acceptance": str(docs)},
        }
        brain = Brain(config)
        brain.capture(
            {
                "scope": "personal",
                "id": "fixture",
                "event_id": "fixture",
                "type": "knowledge",
                "status": "verified",
                "source_agent": "codex",
                "title": "Synthetic fixture",
                "body": "Synthetic browser acceptance",
                "evidence": "Disposable local fixture",
            }
        )
        preserved = {
            p: p.read_bytes()
            for base in [brain.vault, brain.state]
            for p in base.rglob("*")
            if p.is_file()
        }
        preserved.update({p: p.read_bytes() for p in docs.glob("*.md") if p != source})
        context = multiprocessing.get_context("spawn")
        process = stop = None

        def shutdown():
            if process:
                stop.set()
                process.join(5)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                assert not process.is_alive(), "Fixture process did not stop"

        def start():
            stop = context.Event()
            parent, child = context.Pipe(duplex=False)
            process = context.Process(target=serve, args=(config, child, stop))
            process.start()
            child.close()
            assert parent.poll(15), "Fixture server did not start"
            url = parent.recv()
            parent.close()
            return process, stop, url

        reports = []
        state = {}
        try:
            process, stop, url = start()
            for phase in ["create", "restart", "reattached", "ambiguous", "orphan", "touch"]:
                print(json.dumps({"phase": phase, "status": "started"}), flush=True)
                if phase == "restart":
                    shutdown()
                    process, stop, url = start()
                if phase == "reattached":
                    source.write_text(BODY.replace(PROSE, f"**{PROSE}**"), encoding="utf-8")
                if phase == "ambiguous":
                    source.write_text(
                        BODY + "\n" + BODY + "\nNueva ubicación confirmada 😀\n", encoding="utf-8"
                    )
                if phase == "orphan":
                    source.unlink()
                if phase == "touch":
                    source.write_text(BODY, encoding="utf-8")
                expected_source = source.read_bytes() if source.exists() else None
                sidecar = brain.state / "annotations.json"
                before_read = sidecar.read_bytes() if phase in {"restart", "reattached"} else None
                request = {
                    "url": url,
                    "phase": phase,
                    "state": state,
                    "prose": PROSE,
                    "command": COMMAND,
                }
                result = subprocess.run(
                    [node, str(script)],
                    input=json.dumps(request),
                    capture_output=True,
                    encoding="utf-8",
                    timeout=90,
                )
                if result.returncode:
                    raise AssertionError(f"{phase}: {result.stderr.replace(url, '<fixture>/')}")
                state = json.loads(result.stdout)
                reports.append({"phase": phase, "checks": state["checks"]})
                assert (source.read_bytes() if source.exists() else None) == expected_source
                if before_read is not None:
                    assert sidecar.read_bytes() == before_read
                assert all(p.read_bytes() == content for p, content in preserved.items())
            exported = Annotations(brain).export()
            recovered = Brain(
                {
                    **config,
                    "vault_path": str(root / "recovered-vault"),
                    "state_path": str(root / "recovered-state"),
                }
            )
            Annotations(recovered).restore(json.dumps(exported))
            assert Annotations(recovered).export() == exported
            assert all(p.read_bytes() == content for p, content in preserved.items())
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "phases": reports,
                        "export_restore": "exact",
                        "source_ledger_note_bytes": "preserved",
                        "data": "synthetic",
                        "touch": "browser emulation, not physical phone",
                        "highlight_contrast": state["contrast"],
                    }
                )
            )
        finally:
            shutdown()


if __name__ == "__main__":
    main()
