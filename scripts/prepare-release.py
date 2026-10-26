"""Prepare a version-matched, allowlisted alpha bundle; no GitHub writes."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path


def prepare(root):
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    # shortcut: alpha releases only; extend mapping explicitly before shipping beta/stable versions.
    match = re.fullmatch(r"(\d+\.\d+\.\d+)a(\d+)", version)
    if not match:
        raise ValueError("Only explicit PEP440 alpha versions are supported")
    tag = f"v{match[1]}-alpha.{match[2]}"
    notes = f"docs/releases/{tag}.md"
    if not (root / notes).is_file():
        raise ValueError("Version-matched release notes are required")
    wheel = f"second_brain-{version}-py3-none-any.whl"
    sdist = f"second_brain-{version}.tar.gz"
    constraints = f"second_brain-{version}-constraints.txt"
    dist = root / "dist"
    forbidden = {
        "vault",
        "state",
        "backups",
        ".runtime",
        ".venv",
        ".release-env",
        "artifacts",
        ".git",
    }
    with zipfile.ZipFile(dist / wheel) as archive:
        names = archive.namelist()
        if any(
            not name.startswith(("second_brain/", f"second_brain-{version}.dist-info/"))
            for name in names
        ):
            raise ValueError("Unexpected wheel paths")
        metadata = BytesParser().parsebytes(
            archive.read(f"second_brain-{version}.dist-info/METADATA")
        )
        if metadata["Version"] != version or metadata["Name"] != "second-brain":
            raise ValueError("Wheel metadata does not match project version/name")
        if archive.read("second_brain/resources/second-brain/SKILL.md") != (
            root / "skills/second-brain/SKILL.md"
        ).read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("Packaged skill differs from canonical source")
    with tarfile.open(dist / sdist) as archive:
        members = archive.getmembers()
        if any(not item.isfile() and not item.isdir() for item in members):
            raise ValueError("Source archive contains links or special files")
        source_names = [item.name for item in members]
        if any(not name.startswith(f"second_brain-{version}/") for name in source_names):
            raise ValueError("Unexpected source root")
        tracked = set(
            subprocess.run(
                ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True
            ).stdout.split("\0")
        )
        for item in members:
            relative = item.name.removeprefix(f"second_brain-{version}/")
            if not item.isfile() or relative == "PKG-INFO":
                continue
            if relative not in tracked:
                raise ValueError("Untracked file in source archive")
            if archive.extractfile(item).read().replace(b"\r\n", b"\n") != (
                root / relative
            ).read_bytes().replace(b"\r\n", b"\n"):
                raise ValueError("Source archive differs from reviewed source")
    for name in names + source_names:
        parts = set(name.split("/"))
        if parts & forbidden or ".." in parts or "\\" in name or name.startswith("/"):
            raise ValueError("Unsafe/private artifact directory")
    exported = subprocess.run(
        ["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--no-hashes"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    (dist / constraints).write_text(exported.stdout, encoding="utf-8")
    names = [wheel, sdist, constraints]
    (dist / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((dist / name).read_bytes()).hexdigest()}  {name}\n" for name in names
        ),
        encoding="utf-8",
    )
    return {"tag": tag, "wheel": wheel, "sdist": sdist, "constraints": constraints, "notes": notes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    result = prepare(Path.cwd())
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in result.items()))
    print(json.dumps(result))
