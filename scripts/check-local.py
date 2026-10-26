"""Routine source checks, with the current interpreter; no hosted runs or deployment changes."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-repository.py")], cwd=ROOT, check=True
    )
    commands = [
        ["ruff", "check", "src", "tests", "scripts"],
        ["ruff", "format", "--check", "src", "tests", "scripts"],
        ["pytest", "-q"],
        ["second_brain.cli", "--help"],
    ]
    for command in commands:
        print("Checking: " + " ".join(command), flush=True)
        subprocess.run(
            [sys.executable, "-m", *command],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL if command[0] == "second_brain.cli" else None,
        )
    print("Local source checks passed. Package/host/browser checks are separate when relevant.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
