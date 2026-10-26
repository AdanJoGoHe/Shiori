"""Fetch published Shiori releases; reuse the versioned runtime for activation."""

import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from filelock import FileLock
from packaging.version import Version

from second_brain import runtime
from second_brain.core import scoped_path

REPOSITORY = "AdanJoGoHe/Shiori"
API = f"https://api.github.com/repos/{REPOSITORY}"
HOSTS = {
    "api.github.com",
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}


def trusted_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("Update download left the approved HTTPS hosts")
    return url


class ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        trusted_url(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


def fetch(url, limit, *, binary=False):
    request = Request(
        trusted_url(url),
        headers={
            "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
            "User-Agent": "Shiori-updater",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    try:
        with build_opener(ReleaseRedirects()).open(request, timeout=20) as response:
            trusted_url(response.geturl())
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("Update response exceeds its size limit")
            return raw
    except HTTPError as error:
        if error.code == 404 and url == API + "/releases/latest":
            return b"null"
        if error.code in {403, 429}:
            raise ValueError(
                "GitHub refused the update check or rate limited it; retry later"
            ) from None
        raise ValueError("GitHub update request failed") from None
    except (URLError, OSError):
        raise ValueError(
            "Cannot reach GitHub for updates; check the connection and retry"
        ) from None


def release_version(release):
    if (
        not isinstance(release, dict)
        or release.get("draft") is not False
        or type(release.get("prerelease")) is not bool
        or not release.get("published_at")
    ):
        return None
    match = re.fullmatch(
        r"v(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?", str(release.get("tag_name"))
    )
    if not match:
        return None
    version = Version(
        match[1]
        + ({"alpha": "a", "beta": "b", "rc": "rc"}[match[2]] + match[3] if match[2] else "")
    )
    if version.is_prerelease != release["prerelease"]:
        raise ValueError("Release channel and version do not match")
    if (
        not isinstance(release["published_at"], str)
        or datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).tzinfo is None
    ):
        raise ValueError("Invalid published release timestamp")
    return version


def select_release(current, prerelease=False):
    endpoint = "/releases?per_page=100" if prerelease else "/releases/latest"
    try:
        payload = json.loads(fetch(API + endpoint, 2_000_000))
    except (json.JSONDecodeError, RecursionError):
        raise ValueError("Invalid GitHub release response") from None
    if prerelease:
        if not isinstance(payload, list) or len(payload) > 100:
            raise ValueError("Invalid published release list")
        releases = payload
    else:
        releases = [] if payload is None else [payload]
    eligible = []
    for release in releases:
        version = release_version(release)
        if version is not None and (prerelease or not version.is_prerelease):
            eligible.append((version, release))
    if not eligible:
        return {
            "status": "no-published-release",
            "applied": False,
            "channel": "prerelease" if prerelease else "stable",
        }, None
    version, release = max(eligible, key=lambda item: item[0])
    result = {
        "status": "available" if version > Version(current) else "up-to-date",
        "applied": False,
        "from": current,
        "to": str(version),
        "release": f"https://github.com/{REPOSITORY}/releases/tag/{release['tag_name']}",
    }
    return result, release


def release_assets(release, version):
    names = {
        f"second_brain-{version}-py3-none-any.whl": 8_000_000,
        f"second_brain-{version}-constraints.txt": 128000,
        "SHA256SUMS": 128000,
    }
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) > 100:
        raise ValueError("Invalid release assets")
    selected = {}
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Invalid release asset")
        name = asset.get("name")
        if not isinstance(name, str):
            raise ValueError("Invalid release asset name")
        if name not in names:
            continue
        if (
            name in selected
            or type(asset.get("id")) is not int
            or asset["id"] <= 0
            or type(asset.get("size")) is not int
            or not 0 < asset["size"] <= names[name]
            or asset.get("state") != "uploaded"
            or not isinstance(asset.get("digest"), str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", asset["digest"])
        ):
            raise ValueError("Missing, duplicate or invalid release asset metadata")
        selected[name] = asset
    if set(selected) != set(names):
        raise ValueError("Release is missing its wheel, constraints or checksums")
    return selected


def refresh_skill(root):
    receipt = scoped_path(root, "augment-skill.json")
    if not receipt.exists():
        return "not-configured"
    try:
        owned = json.loads(runtime.read_file(receipt))
        target = Path(owned["path"])
        if target.name != "SKILL.md" or target.parent.name != "shiori-work":
            raise ValueError("Unexpected owned skill target")
        if runtime.digest(runtime.read_file(target)) != owned["sha256"]:
            raise ValueError("Owned skill edited")
        active, _ = runtime.manifest(root)
        runtime.command(
            [
                runtime.python_in(root, active["active"]),
                "-I",
                "-m",
                "second_brain.runtime",
                "--root",
                root,
                "augment",
                "--skills-dir",
                target.parent.parent,
                "--apply",
            ]
        )
        return "updated"
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return "manual-reconciliation-required"


def update(root, *, prerelease=False, apply=False):
    data, _ = runtime.manifest(root)
    result, release = select_release(data["active"], prerelease)
    if result["status"] != "available":
        return result
    assets = release_assets(release, result["to"])
    result["download_bytes"] = sum(asset["size"] for asset in assets.values())
    if not apply:
        return result
    with FileLock(scoped_path(root, "management.lock"), timeout=5):
        runtime.check_idle(root)
        if runtime.manifest(root)[0] != data:
            raise ValueError("Installation changed; check for updates again")
    with tempfile.TemporaryDirectory(prefix=".update-", dir=root) as directory:
        directory = Path(directory)
        for name, asset in assets.items():
            raw = fetch(f"{API}/releases/assets/{asset['id']}", asset["size"], binary=True)
            if len(raw) != asset["size"] or hashlib.sha256(raw).hexdigest() != asset[
                "digest"
            ].removeprefix("sha256:"):
                raise ValueError("Downloaded release asset failed integrity checks")
            with scoped_path(directory, name).open("xb") as stream:
                stream.write(raw)
        bundle = runtime.release_bundle(directory)
        if bundle["version"] != result["to"]:
            raise ValueError("Downloaded package version does not match selected release")
        applied = runtime.change_version(root, directory, apply=True)
    return {**result, **applied, "skill": refresh_skill(root)}
