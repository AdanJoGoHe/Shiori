"""Optional real-browser acceptance; owns only a disposable synthetic deployment."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from second_brain.core import Brain
from second_brain.viewer import ViewerServer


def main():
    node = os.environ.get("SB_TEST_NODE") or shutil.which("node")
    if not node:
        raise SystemExit("Set SB_TEST_NODE; preinstall Playwright and a browser")
    with tempfile.TemporaryDirectory(prefix="sb-explorer-acceptance-") as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert root.name.startswith("sb-explorer-acceptance-")
        docs = root / "docs"
        docs.mkdir()
        (root / "empty").mkdir()
        for number in range(25):
            (docs / f"guide-{number:02}.md").write_text(
                f"---\nproject: acceptance\ntags: [synthetic]\n---\n# Guide {number:02}\n\n"
                "SB-EXPLORER-ACCEPTANCE. Datos sintéticos.\n\n"
                "## Comandos\n\n```powershell\ngit --version\n```\n\n"
                "| Campo | Valor |\n|---|---|\n| IP | 192.0.2.44 |\n\n"
                "[Siguiente guía](guide-01.md)\n\n[Fuera](../private.md)\n\n"
                "<script>globalThis.fixtureExecuted=true</script>\n\n"
                "![Remota](https://example.test/image)\n\n"
                "[Ejecutar](javascript:alert(1))\n\n"
                + (
                    "Texto sintético para medir lectura y renderizado.\n\n" * 400
                    if number == 0
                    else ""
                ),
                encoding="utf-8",
            )
        (docs / "invalid.md").write_bytes(b"\xff")
        (docs / "oversized.md").write_bytes(b"x" * 1_000_001)
        (root / "private.md").write_text("OUTSIDE-SENTINEL", encoding="utf-8")
        brain = Brain(
            {
                "scope": "personal",
                "timezone": "Europe/Madrid",
                "vault_path": str(root / "vault"),
                "state_path": str(root / "state"),
                "documentation_roots": {"acceptance": str(docs), "empty": str(root / "empty")},
            }
        )
        for note_id in ["command", "other"]:
            assert (
                brain.capture(
                    {
                        "scope": "personal",
                        "id": note_id,
                        "event_id": note_id,
                        "type": "command",
                        "status": "verified",
                        "source_agent": "codex",
                        "title": "Synthetic " + note_id,
                        "body": "git --version\n\n[[other]]",
                        "evidence": "Synthetic observable evidence",
                        "tags": ["synthetic", "windows"],
                        "project": "acceptance",
                    }
                )["status"]
                == "saved"
            )
        preserved = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
        request = {"profile": str(root / "browser"), "date": brain.now().date().isoformat()}
        reports = []
        port = 0
        # The explorer must never need the provider/index, even when it is unavailable.
        with patch(
            "second_brain.provider.provider_search", side_effect=AssertionError("Provider used")
        ):
            for phase in ["browse", "restart"]:
                print(json.dumps({"phase": phase, "status": "started"}), flush=True)
                with ViewerServer(brain, port) as server:
                    port = server.server_port
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        result = subprocess.run(
                            [node, str(Path(__file__).with_suffix(".cjs"))],
                            input=json.dumps({**request, "url": server.url, "phase": phase}),
                            capture_output=True,
                            encoding="utf-8",
                            timeout=120,
                        )
                        if result.returncode:
                            raise AssertionError(result.stderr.replace(server.url, "<fixture>/"))
                        reports.append(json.loads(result.stdout))
                        if phase == "browse":
                            states = subprocess.run(
                                [node, str(Path(__file__).with_name("check-viewer-states.cjs"))],
                                env={**os.environ, "SB_VIEWER_TEST_URL": server.url},
                                capture_output=True,
                                encoding="utf-8",
                                timeout=120,
                            )
                            if states.returncode:
                                raise AssertionError(
                                    states.stderr.replace(server.url, "<fixture>/")
                                )
                            reports.append({"states": states.stdout.strip()})
                    finally:
                        server.shutdown()
                        thread.join(5)
                        assert not thread.is_alive()
        assert all(p.read_bytes() == content for p, content in preserved.items())
        assert not (brain.state / "annotations.json").exists()
        print(
            json.dumps(
                {
                    "status": "passed",
                    "reports": reports,
                    "source_note_ledger_bytes": "preserved",
                    "provider": "unused",
                    "guide_bytes": (docs / "guide-00.md").stat().st_size,
                }
            )
        )


if __name__ == "__main__":
    main()
