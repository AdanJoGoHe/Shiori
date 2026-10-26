import shutil
import subprocess
from pathlib import Path

import pytest


def test_browser_annotation_offset_and_overlap_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is only needed for frontend development checks")
    result = subprocess.run(
        [node, "--test", "scripts/test-reader-marks.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
