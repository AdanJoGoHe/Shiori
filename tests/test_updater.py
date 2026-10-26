import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from filelock import FileLock

from second_brain import runtime, updater
from test_runtime import bundle, managed as managed_fixture


@pytest.fixture
def managed(tmp_path, monkeypatch):
    return managed_fixture.__wrapped__(tmp_path, monkeypatch)


def published(tag="v1.2.3-alpha.5", **changes):
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": "-" in tag,
        "published_at": "2026-10-26T00:00:00Z",
        "assets": [],
        **changes,
    }


def feed_release(monkeypatch, directory):
    version = runtime.release_bundle(directory)["version"]
    release = published(f"v{version.split('a')[0]}-alpha.{version.split('a')[1]}")
    payloads = {}
    for index, path in enumerate(sorted(directory.iterdir()), 1):
        raw = path.read_bytes()
        release["assets"].append(
            {
                "id": index,
                "name": path.name,
                "state": "uploaded",
                "size": len(raw),
                "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        )
        payloads[f"{updater.API}/releases/assets/{index}"] = raw
    calls = []

    def fetch(url, limit, *, binary=False):
        calls.append((url, binary))
        return payloads[url] if binary else json.dumps([release]).encode()

    monkeypatch.setattr(updater, "fetch", fetch)
    return release, payloads, calls


def test_channels_filter_drafts_and_choose_highest_version(monkeypatch):
    releases = [
        published("v1.2.3-alpha.99", draft=True),
        published("v1.2.3-alpha.5"),
        published("v1.2.2"),
        published("v1.2.3-alpha.6"),
        published("v9.0.0", published_at=None),
        published("unsupported-tag"),
    ]
    monkeypatch.setattr(updater, "fetch", lambda *a, **k: json.dumps(releases).encode())
    result, release = updater.select_release("1.2.3a4", prerelease=True)
    assert result["status"] == "available" and result["to"] == "1.2.3a6"
    assert release["tag_name"] == "v1.2.3-alpha.6"
    monkeypatch.setattr(updater, "fetch", lambda *a, **k: json.dumps(published("v1.2.3")).encode())
    assert updater.select_release("1.2.3a6")[0]["to"] == "1.2.3"


@pytest.mark.parametrize("payload", [None, published("v1.2.3-alpha.5")])
def test_default_channel_never_installs_prereleases(monkeypatch, payload):
    monkeypatch.setattr(updater, "fetch", lambda *a, **k: json.dumps(payload).encode())
    assert updater.select_release("1.2.3a4")[0]["status"] == "no-published-release"


def test_equal_or_older_version_does_not_download(managed, monkeypatch, tmp_path):
    root, _, _ = managed
    _, _, calls = feed_release(monkeypatch, bundle(tmp_path / "older", "1.2.3a3"))
    assert updater.update(root, prerelease=True, apply=True)["status"] == "up-to-date"
    assert len(calls) == 1 and not calls[0][1]


def test_preview_has_no_writes_or_asset_downloads(managed, monkeypatch, tmp_path):
    root, _, _ = managed
    _, _, calls = feed_release(monkeypatch, bundle(tmp_path / "next", "1.2.3a5"))
    before = {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    result = updater.update(root, prerelease=True)
    assert result["status"] == "available" and result["download_bytes"] > 0
    assert len(calls) == 1 and not calls[0][1]
    assert before == {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_online_apply_uses_verified_bundle_and_preserves_notes(managed, monkeypatch, tmp_path):
    root, brain, _ = managed
    content = brain.read("git-version")
    _, _, calls = feed_release(monkeypatch, bundle(tmp_path / "next", "1.2.3a5"))
    result = updater.update(root, prerelease=True, apply=True)
    assert result["status"] == "updated" and result["skill"] == "not-configured"
    assert runtime.manifest(root)[0]["active"] == "1.2.3a5"
    assert brain.read("git-version") == content
    assert len([call for call in calls if call[1]]) == 3
    assert not list(root.glob(".update-*"))


def test_live_session_refuses_even_downloading(managed, monkeypatch, tmp_path):
    root, _, _ = managed
    _, _, calls = feed_release(monkeypatch, bundle(tmp_path / "next", "1.2.3a5"))
    sessions = root / "sessions"
    sessions.mkdir()
    with FileLock(sessions / ("b" * 32 + ".lease")):
        with pytest.raises(ValueError, match="Close all managed"):
            updater.update(root, prerelease=True, apply=True)
    assert len(calls) == 1 and runtime.manifest(root)[0]["active"] == "1.2.3a4"


@pytest.mark.parametrize(
    "damage", ["bytes", "digest", "checksum", "missing", "duplicate", "oversized", "name"]
)
def test_invalid_assets_never_activate(managed, monkeypatch, tmp_path, damage):
    root, brain, calls = managed
    release, payloads, _ = feed_release(monkeypatch, bundle(tmp_path / "next", "1.2.3a5"))
    asset = next(item for item in release["assets"] if item["name"].endswith(".whl"))
    if damage == "bytes":
        payloads[f"{updater.API}/releases/assets/{asset['id']}"] = b"corrupt"
    elif damage == "digest":
        asset["digest"] = "sha256:" + "0" * 64
    elif damage == "checksum":
        hashes = next(item for item in release["assets"] if item["name"] == "SHA256SUMS")
        url = f"{updater.API}/releases/assets/{hashes['id']}"
        payloads[url] = payloads[url].replace(asset["digest"][7:].encode(), b"0" * 64)
        hashes["digest"] = "sha256:" + hashlib.sha256(payloads[url]).hexdigest()
    elif damage == "missing":
        release["assets"].remove(asset)
    elif damage == "duplicate":
        release["assets"].append(dict(asset))
    elif damage == "oversized":
        asset["size"] = 8_000_001
    else:
        asset["name"] = "../../outside.whl"
    before = (root / "installation.json").read_bytes()
    count = len(calls)
    with pytest.raises(ValueError):
        updater.update(root, prerelease=True, apply=True)
    assert (root / "installation.json").read_bytes() == before and len(calls) == count
    assert brain.read("git-version")
    assert not list(root.glob(".update-*"))


def test_owned_skill_refresh_preserves_edited_file(managed, tmp_path):
    root, _, calls = managed
    skills = tmp_path / "home/.augment/skills"
    result = runtime.augment(root, skills, apply=True)
    assert updater.refresh_skill(root) == "updated"
    assert "augment" in calls[-1]
    target = Path(result["skill"])
    target.write_text("user edit")
    count = len(calls)
    assert updater.refresh_skill(root) == "manual-reconciliation-required"
    assert target.read_text() == "user edit" and len(calls) == count
    (root / "augment-skill.json").write_text("[]")
    assert updater.refresh_skill(root) == "manual-reconciliation-required"
    assert target.read_text() == "user edit" and len(calls) == count


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/x",
        "https://other.invalid/x",
        "https://api.github.com@other.invalid/x",
        "https://user@api.github.com/x",
        "https://api.github.com:444/x",
        "file:///tmp/asset",
    ],
)
def test_redirects_cannot_leave_approved_https_hosts(url):
    request = Request(updater.API)
    with pytest.raises(ValueError):
        updater.ReleaseRedirects().redirect_request(request, None, 302, "Found", {}, url)


def test_fetch_is_bounded_and_does_not_read_authentication(monkeypatch):
    observed = []

    class Response(io.BytesIO):
        def geturl(self):
            return "https://release-assets.githubusercontent.com/synthetic"

    class Opener:
        def open(self, request, timeout):
            observed.append(request)
            assert timeout == 20
            return Response(b"x" * 11)

    monkeypatch.setenv("GH_TOKEN", "synthetic-not-used")
    monkeypatch.setattr(updater, "build_opener", lambda *args: Opener())
    with pytest.raises(ValueError, match="size limit"):
        updater.fetch(updater.API, 10, binary=True)
    assert not any(key.lower() == "authorization" for key in observed[0].headers)


@pytest.mark.parametrize("code", [403, 429, 500, None])
def test_network_failures_are_controlled_without_response_bodies(monkeypatch, code):
    class Opener:
        def open(self, request, timeout):
            if code:
                raise HTTPError(
                    request.full_url, code, "private response", {}, io.BytesIO(b"private body")
                )
            raise URLError("private proxy address")

    monkeypatch.setattr(updater, "build_opener", lambda *args: Opener())
    with pytest.raises(ValueError) as error:
        updater.fetch(updater.API, 100)
    assert "private" not in str(error.value)


def test_no_stable_release_is_a_normal_check_result(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO())

    monkeypatch.setattr(updater, "build_opener", lambda *args: Opener())
    assert updater.select_release("1.2.3a4")[0]["status"] == "no-published-release"
