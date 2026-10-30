"""Stable, standard-library-only entry point copied into a managed installation."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).absolute().parent
    manifest = root / "installation.json"
    if manifest.stat().st_size > 16000:
        raise ValueError("Oversized installation manifest")
    active = json.loads(manifest.read_text(encoding="utf-8"))["active"]
    if not isinstance(active, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", active):
        raise ValueError("Invalid active version")
    interpreter = (
        root / "versions" / active / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if any(
        path.is_symlink() or path.is_junction()
        for path in [interpreter.parent, *interpreter.parent.parents]
    ):
        raise ValueError("Linked installation root")
    result = subprocess.call(
        [str(interpreter), "-I", "-m", "second_brain.runtime", "--root", str(root), *sys.argv[1:]]
    )
    if result and sys.argv[1:3] == ["run", "serve"]:
        print(
            "Shiori MCP did not start or exited with an error. Backup CLI in the same installation: "
            + str(root / "shiori.cmd")
            + " run status. If unavailable too, inspect this installation's active interpreter/manifest; do not switch profiles.",
            file=sys.stderr,
        )
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError):
        print(
            "Shiori: cannot open the managed installation; inspect its manifest and active interpreter. "
            "Backup CLI: shiori.cmd run status in this same installation. "
            "Do not switch personal/work profiles; preserve original capture JSON/event IDs after timeouts.",
            file=sys.stderr,
        )
        raise SystemExit(1)
