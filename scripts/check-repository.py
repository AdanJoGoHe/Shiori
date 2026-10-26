"""Check publishable source or the exact Git index; never print matched content."""

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


ROOT_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
    "uv.lock",
}
SUFFIXES = {
    "src": {".py", ".js", ".css", ".html"},
    "tests": {".py"},
    "scripts": {".py", ".ps1", ".cjs"},
    "docs": {".md"},
    "adapters": {".md"},
    "skills": {".md"},
    "templates": {".md"},
    "assets": {".svg"},
    ".github": {".md", ".yml"},
}
HOOKS = {"pre-commit", "commit-msg"}
PRIVATE_PARTS = {
    "vault",
    "state",
    "backups",
    "artifacts",
    "reports",
    "local",
    "node_modules",
    ".git",
    ".venv",
    ".runtime",
    "runtime",
    "__pycache__",
    ".ssh",
}
MAX_BYTES = 2 * 1024 * 1024
MOJIBAKE = re.compile(r"\u00c3[\u0080-\u00bf]|\u00c2[\u0080-\u00bf]|\u00e2\u20ac|\ufffd")
PERSONAL_PATH = re.compile(r"(?i)[a-z]:[/\\]Users[/\\](?!USER(?:[/\\]|$))[^/\\\s<>]+")


def file_issues(name, raw, mode="100644"):
    path = PurePosixPath(name)
    issues = []
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", name) or ".." in path.parts:
        issues.append("unexpected filename")
    if set(part.casefold() for part in path.parts) & PRIVATE_PARTS:
        issues.append("private/runtime directory")
    allowed = (
        name in ROOT_FILES
        if len(path.parts) == 1
        else (
            path.parts[0] == "config"
            and name.endswith(".example.json")
            or path.parts[0] == ".githooks"
            and path.name in HOOKS
            or path.suffix in SUFFIXES.get(path.parts[0], set())
        )
    )
    if not allowed:
        issues.append("file outside source allowlist")
    if mode not in {"100644", "100755"}:
        issues.append("links/submodules/special files are not source")
    if len(raw) > MAX_BYTES:
        return issues + ["file exceeds 2 MiB review limit"]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return issues + ["non-UTF-8 or binary content"]
    for number, line in enumerate(text.split("\n"), 1):
        if any(unicodedata.category(c) in {"Cc", "Cf"} and c not in "\r\t" for c in line):
            issues.append(f"line {number}: hidden/control character")
        if MOJIBAKE.search(line):
            issues.append(f"line {number}: broken text encoding")
        if PERSONAL_PATH.search(line):
            issues.append(f"line {number}: personal Windows user path")
    if path.suffix == ".svg":
        if re.search(r"(?i)<!DOCTYPE|<!ENTITY|url\s*\(", text):
            return issues + ["active/external SVG content"]
        try:
            tree = ET.fromstring(text)
            if any(
                node.tag.split("}")[-1] in {"script", "foreignObject"}
                or any(key.split("}")[-1].lower().startswith("on") for key in node.attrib)
                or any(
                    key.split("}")[-1] == "href" and not value.startswith("#")
                    for key, value in node.attrib.items()
                )
                for node in tree.iter()
            ):
                issues.append("active/external SVG content")
        except ET.ParseError:
            issues.append("invalid SVG")
    return issues


def message_issues(text):
    return (
        ["commit messages must describe the change without CODEX attribution"]
        if ("codex" in text.casefold())
        else []
    )


def git(root, *args, **kwargs):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, **kwargs)


def source_files(root, staged):
    records = git(root, "ls-files", "--stage", "-z").stdout.split(b"\0")
    entries = []
    for record in filter(None, records):
        metadata, name = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise ValueError("Resolve unmerged index entries before checking publication")
        entries.append((name.decode("utf-8"), mode, oid))
    if staged:
        data = git(
            root,
            "cat-file",
            "--batch",
            input=("".join(oid + "\n" for _, _, oid in entries).encode("ascii")),
        ).stdout
        position = 0
        for name, mode, _ in entries:
            end = data.index(b"\n", position)
            header = data[position:end].split()
            if len(header) != 3 or header[1] != b"blob":
                raise ValueError("Index contains a missing or non-file object")
            size = int(header[2])
            position = end + 1
            yield name, mode, data[position : position + size]
            position += size + 1
    else:
        for name, mode, _ in entries:
            path = root / name
            info = path.lstat()
            parents = [path, *path.relative_to(root).parents]
            linked = any(
                (root / parent).is_symlink() or (root / parent).is_junction() for parent in parents
            )
            if not stat.S_ISREG(info.st_mode) or linked:
                yield name, "special", b""
            else:
                yield name, mode, path.read_bytes()


def secret_scan(root, files):
    configured = subprocess.run(
        ["git", "config", "--get", "shiori.gitleaks"], cwd=root, capture_output=True, text=True
    )
    executable = (
        os.environ.get("SHIORI_GITLEAKS") or configured.stdout.strip() or shutil.which("gitleaks")
    )
    if not executable:
        raise ValueError("Gitleaks is required; see CONTRIBUTING.md for local setup")
    # Scan exact source/index bytes, excluding ignored runtime and developer environments.
    result = subprocess.run(
        [executable, "stdin", "--redact", "--no-banner", "--no-color"],
        input=b"\n".join(raw for _, _, raw in files),
        cwd=root,
        capture_output=True,
    )
    if result.returncode:
        raise ValueError("Secret scan failed; inspect privately with Gitleaks --redact")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--secrets", action="store_true")
    parser.add_argument("--message-file", type=Path)
    args = parser.parse_args()
    if args.message_file:
        problems = message_issues(args.message_file.read_text(encoding="utf-8-sig"))
    else:
        root = Path(__file__).resolve().parents[1]
        files = list(source_files(root, args.staged))
        problems = [
            f"{name!r}: {issue}"
            for name, mode, raw in files
            for issue in file_issues(name, raw, mode)
        ]
        if not problems and args.secrets:
            secret_scan(root, files)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("Repository policy checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f"Repository check could not complete: {reason}", file=sys.stderr)
        raise SystemExit(1) from None
