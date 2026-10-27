"""Versioned installation and updates; data stays outside version environments."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
import zipfile
from contextlib import nullcontext
from email.parser import BytesParser
from importlib.metadata import version as installed_version
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

from filelock import FileLock, Timeout
from packaging.requirements import Requirement
from packaging.version import Version

from second_brain.annotations import Annotations
from second_brain.backup import backup
from second_brain.core import Brain, atomic_write, canonical_root, load_config, scoped_path
from second_brain.provider import project_name
from second_brain.store import check_store

VERSION_TEXT = r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?"
VERSION = re.compile(VERSION_TEXT + r"\Z")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_file(path, limit=128000):
    path = scoped_path(path.parent, path.name)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Oversized managed file")
    return raw


def release_bundle(directory):
    directory = canonical_root(directory)
    lines = read_file(directory / "SHA256SUMS").decode("utf-8").splitlines()
    hashes = {}
    for line in lines:
        match = re.fullmatch(r"([a-f0-9]{64})  ([a-zA-Z0-9_.-]+)", line)
        if not match or match[2] in hashes:
            raise ValueError("Invalid or duplicate release checksums")
        hashes[match[2]] = match[1]
    wheels = [name for name in hashes if name.endswith("-py3-none-any.whl")]
    if len(wheels) != 1:
        raise ValueError("Release must contain exactly one Shiori wheel")
    wheel_name = wheels[0]
    match = re.fullmatch(r"second_brain-(" + VERSION_TEXT + r")-py3-none-any.whl", wheel_name)
    if not match:
        raise ValueError("Unsupported release version or package")
    version = match[1]
    constraints = f"second_brain-{version}-constraints.txt"
    for name, limit in [(wheel_name, 8_000_000), (constraints, 128000)]:
        raw = read_file(directory / name, limit)
        if digest(raw) != hashes.get(name):
            raise ValueError("Release integrity mismatch")
    for line in raw.decode("utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        pins = list(requirement.specifier)
        if requirement.url or len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise ValueError("Release constraints must contain exact registry pins only")
    wheel = directory / wheel_name
    with zipfile.ZipFile(wheel) as archive:
        metadata = BytesParser().parsebytes(
            archive.read(f"second_brain-{version}.dist-info/METADATA")
        )
        if metadata["Name"] != "second-brain" or metadata["Version"] != version:
            raise ValueError("Wheel metadata mismatch")
    return {
        "version": version,
        "wheel": wheel,
        "constraints": directory / constraints,
        "wheel_sha256": hashes[wheel_name],
        "constraints_sha256": hashes[constraints],
    }


def private_root(value):
    root = canonical_root(value)
    if root in {Path.home().resolve(), *Path.home().resolve().parents}:
        raise ValueError("Choose a dedicated installation directory")
    if any((path / ".git").exists() for path in (root, *root.parents)):
        raise ValueError("Installations and memory must stay outside source Git")
    return root


def python_in(root, version):
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Invalid managed version")
    relative = f"versions/{version}/" + ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Venv interpreter symlinks are normal on Unix; installation ancestors are not.
    parent = scoped_path(root, str(Path(relative).parent))
    return parent / Path(relative).name


def manifest(root):
    data = json.loads(read_file(root / "installation.json", 16000))
    if data.get("schema_version") != 1 or data.get("scope") != "work":
        raise ValueError("Unsupported managed installation")
    python_in(root, data["active"])
    if data.get("previous") is not None:
        python_in(root, data["previous"])
    for name in ["shiori.py", "shiori.cmd"]:
        if digest(read_file(root / name)) != data["launchers"].get(name):
            raise ValueError("Stable launcher changed; reconcile it manually")
    config = load_config(root / "data/config.json")
    expected = configuration(root, config["timezone"])
    if config != expected:
        raise ValueError("Managed configuration paths or scope changed; reconcile manually")
    check_store("work", Path(config["vault_path"]), Path(config["state_path"]))
    Brain(config).ledger()
    return data, config


def configuration(root, timezone):
    ZoneInfo(timezone)
    return {
        "schema_version": 1,
        "scope": "work",
        "timezone": timezone,
        "vault_path": str(root / "data/vault"),
        "state_path": str(root / "data/state"),
        "basic_memory_config_dir": str(root / "data/state/basic-memory"),
    }


def command(arguments):
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "PYTHONHOME",
            "UV_PROJECT",
            "UV_OVERRIDE",
            "UV_CONSTRAINT",
            "UV_CONFIG_FILE",
            "UV_BUILD_CONSTRAINT",
            "UV_WORKING_DIR",
        }
    }
    result = subprocess.run(
        [str(arg) for arg in arguments],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,
    )
    if result.returncode:
        raise ValueError(
            "Package installation or compatibility check failed; active version preserved"
        )


def install_version(root, bundle):
    target = root / "versions" / bundle["version"]
    if target.exists():
        raise ValueError("Version directory already exists; inspect it rather than overwrite it")
    target.parent.mkdir(exist_ok=True)
    command(["uv", "--no-config", "venv", "--python", "3.12", str(target)])
    command(
        [
            "uv",
            "--no-config",
            "pip",
            "install",
            "--python",
            str(python_in(root, bundle["version"])),
            "--constraint",
            bundle["constraints"].as_uri(),
            bundle["wheel"].as_uri(),
        ]
    )


def probe(root, version):
    command(
        [
            python_in(root, version),
            "-I",
            "-m",
            "second_brain.runtime",
            "--root",
            root,
            "probe",
            "--expect-version",
            version,
        ]
    )


def check_idle(root):
    sessions = scoped_path(root, "sessions")
    if not sessions.exists():
        return
    for path in sessions.iterdir():
        if not re.fullmatch(r"[a-f0-9]{32}\.lease", path.name):
            raise ValueError("Unexpected session file; inspect the installation")
        path = scoped_path(sessions, path.name)
        try:
            with FileLock(path, timeout=0):
                pass
        except Timeout:
            raise ValueError("Close all managed MCP/viewer sessions before updating") from None


def checkpoint(root, cfg):
    recovery = scoped_path(root, f"recovery/{uuid.uuid4().hex}")
    recovery.mkdir(parents=True)
    for name, path in [
        ("installation.json", root / "installation.json"),
        ("config.json", root / "data/config.json"),
        ("shiori.py", root / "shiori.py"),
        ("shiori.cmd", root / "shiori.cmd"),
    ]:
        (recovery / name).write_bytes(read_file(path))
    backup(Brain(cfg), recovery / "memory")
    return recovery


def candidate_launchers(root, version):
    result = subprocess.run(
        [
            str(python_in(root, version)),
            "-I",
            "-X",
            "utf8",
            "-c",
            "import json,sys; from pathlib import Path; import second_brain.launcher as module; "
            "print(json.dumps({'source':Path(module.__file__).read_text(encoding='utf-8'),"
            "'base':sys._base_executable}))",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if result.returncode:
        raise ValueError("Cannot inspect candidate launcher; active version preserved")
    info = json.loads(result.stdout)
    source, base = info["source"], info["base"]
    if not isinstance(source, str) or len(source) > 128000 or not isinstance(base, str):
        raise ValueError("Invalid candidate launcher")
    if any(c in base for c in '%\r\n"'):
        raise ValueError("Unsupported character in Windows interpreter path")
    return {
        "shiori.py": source,
        "shiori.cmd": f'@echo off\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n"{base}" -I "%~dp0shiori.py" %*\nexit /b %errorlevel%\n',
    }


def install(root, directory, timezone="UTC", apply=False):
    bundle = release_bundle(directory)
    if root.exists():
        raise ValueError("Install requires a new directory; existing installations use update")
    cfg = configuration(root, timezone)
    result = {
        "status": "ready",
        "applied": False,
        "scope": "work",
        "version": bundle["version"],
        "root": str(root),
    }
    if not apply:
        return result
    root.mkdir(parents=True)
    with FileLock(root / "management.lock", timeout=5):
        install_version(root, bundle)
        brain = Brain(cfg)
        provider = Path(cfg["basic_memory_config_dir"])
        provider.mkdir()
        project = project_name(cfg)
        atomic_write(
            provider / "config.json",
            json.dumps(
                {
                    "projects": {project: {"path": str(brain.vault), "mode": "local"}},
                    "default_project": project,
                    "semantic_search_enabled": False,
                    "logfire_enabled": False,
                    "logfire_send_to_logfire": False,
                    "auto_update": False,
                }
            ),
        )
        atomic_write(root / "data/config.json", json.dumps(cfg, indent=2))
        probe(root, bundle["version"])
        launcher = Path(__file__).with_name("launcher.py").read_text(encoding="utf-8")
        base = str(Path(sys._base_executable).absolute())
        if any(c in base + str(root) for c in '%\r\n"'):
            raise ValueError("Unsupported character in Windows launcher path")
        shim = f'@echo off\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n"{base}" -I "%~dp0shiori.py" %*\nexit /b %errorlevel%\n'
        launchers = {"shiori.py": launcher, "shiori.cmd": shim}
        for name, content in launchers.items():
            atomic_write(root / name, content)
        data = {
            "schema_version": 1,
            "scope": "work",
            "active": bundle["version"],
            "previous": None,
            "launchers": {name: digest(content.encode()) for name, content in launchers.items()},
        }
        atomic_write(root / "installation.json", json.dumps(data, indent=2))
    return {**result, "status": "installed", "applied": True}


def change_version(root, directory=None, apply=False):
    data, cfg = manifest(root)
    bundle = release_bundle(directory) if directory else None
    target = bundle["version"] if bundle else data.get("previous")
    if not target:
        raise ValueError("No previous version available")
    if target == data["active"]:
        return {"status": "up-to-date", "applied": False, "version": target}
    if bundle and Version(target) <= Version(data["active"]):
        raise ValueError("Updates require a newer version; use rollback for the previous one")
    result = {"status": "ready", "applied": False, "from": data["active"], "to": target}
    if not apply:
        return result
    with FileLock(scoped_path(root, "management.lock"), timeout=5):
        current, current_cfg = manifest(root)
        if current != data or current_cfg != cfg:
            raise ValueError("Installation changed; preview again")
        check_idle(root)
        if bundle:
            install_version(root, bundle)
        recovery = checkpoint(root, cfg)
        probe(root, target)
        launchers = candidate_launchers(root, target)
        originals = {name: read_file(root / name).decode("utf-8") for name in launchers}
        data.update(active=target, previous=data["active"])
        data["launchers"] = {name: digest(content.encode()) for name, content in launchers.items()}
        written = []
        try:
            for name, content in launchers.items():
                atomic_write(root / name, content)
                written.append(name)
            atomic_write(root / "installation.json", json.dumps(data, indent=2))
        except OSError:
            for name in reversed(written):
                atomic_write(root / name, originals[name])
            raise
    return {
        **result,
        "status": "updated" if bundle else "rolled-back",
        "applied": True,
        "recovery": str(recovery),
        "restart_required": True,
    }


def run(root, arguments):
    if not arguments or arguments[0] not in {
        "serve",
        "viewer",
        "status",
        "doctor",
        "search",
        "context",
        "read",
        "capture",
        "classify",
        "pending",
        "pause",
        "resume",
        "catalog",
        "backup",
        "export-memory",
        "import-memory",
        "learn",
    }:
        raise ValueError("Choose a supported Shiori command after run")
    if any(arg == "--config" or arg.startswith("--config=") for arg in arguments):
        raise ValueError("Managed sessions always use their own configuration")
    with FileLock(scoped_path(root, "management.lock"), timeout=5):
        data, _ = manifest(root)
        if installed_version("second-brain") != data["active"]:
            raise ValueError("Active version changed; retry through the stable launcher")
        sessions = scoped_path(root, "sessions")
        sessions.mkdir(exist_ok=True)
        lease = FileLock(sessions / f"{uuid.uuid4().hex}.lease", timeout=0)
        lease.acquire()
    try:
        return subprocess.call(
            [
                str(python_in(root, data["active"])),
                "-I",
                "-m",
                "second_brain.cli",
                "--config",
                str(root / "data/config.json"),
                *arguments,
            ]
        )
    finally:
        lease.release()


def augment(root, skills_dir, apply=False):
    manifest(root)
    target = scoped_path(canonical_root(skills_dir), "shiori-work/SKILL.md")
    source = files("second_brain").joinpath("resources/shiori-work/SKILL.md")
    if not source.is_file():
        source = Path(__file__).resolve().parents[2] / "skills/shiori-work/SKILL.md"
    skill = source.read_text(encoding="utf-8")
    receipt = root / "augment-skill.json"
    if target.exists():
        owned = json.loads(read_file(receipt)) if receipt.exists() else {}
        if owned.get("path") != str(target) or owned.get("sha256") != digest(read_file(target)):
            raise ValueError("Existing Augment skill is unowned or edited; reconcile manually")
    result = {
        "name": "shiori_work",
        "command": f'"{sys._base_executable}" -I "{root / "shiori.py"}" run serve',
        "skill": str(target),
        "applied": False,
    }
    if apply:
        # A receipt precedes the owned write; it cannot authorize overwriting an edited file.
        atomic_write(receipt, json.dumps({"path": str(target), "sha256": digest(skill.encode())}))
        atomic_write(target, skill)
        result["applied"] = True
    return result


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ["install", "update", "rollback", "augment"]:
        item = sub.add_parser(name)
        item.add_argument("--apply", action="store_true")
        if name in {"install", "update"}:
            item.add_argument("--release-dir", type=Path, required=name == "install")
        if name == "update":
            item.add_argument(
                "--prerelease", action="store_true", help="Include published alpha/beta/rc versions"
            )
        if name == "install":
            item.add_argument("--timezone", default="UTC")
        if name == "augment":
            item.add_argument("--skills-dir", type=Path, default=Path.home() / ".augment/skills")
    sub.add_parser("status")
    probe_parser = sub.add_parser("probe")
    probe_parser.add_argument("--expect-version", required=True)
    sub.add_parser("run").add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        root = private_root(args.root)
        if args.action == "install":
            result = install(root, args.release_dir, args.timezone, args.apply)
        elif args.action in {"update", "rollback"}:
            if args.action == "update" and args.release_dir is None:
                from second_brain.updater import update

                result = update(root, prerelease=args.prerelease, apply=args.apply)
            else:
                if args.action == "update" and args.prerelease:
                    raise ValueError("Use --prerelease only for online release checks")
                result = change_version(root, getattr(args, "release_dir", None), args.apply)
        elif args.action == "augment":
            with (
                FileLock(scoped_path(root, "management.lock"), timeout=5)
                if args.apply
                else nullcontext()
            ):
                result = augment(root, args.skills_dir, args.apply)
        elif args.action == "run":
            raise SystemExit(run(root, args.arguments))
        elif args.action == "probe":
            if installed_version("second-brain") != args.expect_version:
                raise ValueError("Installed package version mismatch")
            cfg = load_config(root / "data/config.json")
            if cfg != configuration(root, cfg["timezone"]):
                raise ValueError("Unexpected managed configuration")
            brain = Brain(cfg)
            if brain.status()["pending"]:
                raise ValueError("Resolve pending captures before changing software")
            for note_id in brain.ledger()["notes"]:
                brain.read(note_id)
            Annotations(brain).export()
            result = {"status": "compatible", "scope": brain.scope}
        else:
            data, cfg = manifest(root)
            result = {**data, "memory": Brain(cfg).status()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (
        OSError,
        ValueError,
        KeyError,
        Timeout,
        subprocess.TimeoutExpired,
        zipfile.BadZipFile,
    ) as error:
        print(f"Shiori runtime: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
