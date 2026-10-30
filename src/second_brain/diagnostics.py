"""Same-deployment CLI guidance, never another profile or an automatic write retry."""

import sys
import os
from pathlib import Path


def mcp_fallback(config=None, root=None):
    managed = os.environ.get("SHIORI_MANAGED_ROOT")
    if root is None and managed and config is not None:
        selected = Path(managed)
        if Path(config).absolute() == (selected / "data/config.json").absolute():
            root = selected

    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    command = (
        f"& {quote(root / 'shiori.cmd')} run"
        if root is not None
        else f"& {quote(sys.executable)} -m second_brain.cli --config {quote(config)}"
    )
    return (
        f"MCP backup CLI (same deployment): {command} status\n"
        f"Read-only diagnosis: {command} doctor --catalog\n"
        "A transport failure or timeout does not prove a capture failed. Keep its original "
        f"candidate/event_id; inspect {command} pending before an identical retry. "
        "Do not switch personal/work profiles."
    )
