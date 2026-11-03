import asyncio
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastmcp import Client

from second_brain.annotations import Conflict
from second_brain.backup import backup, restore, read_bundle
from second_brain.core import Brain, load_config
from second_brain.favorites import Favorites, decode
from second_brain.server import create_server
from second_brain.viewer import Viewer, ViewerServer


@pytest.fixture(params=["personal", "work"])
def brain(tmp_path, request):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "# Guía\n\nUsa `echo ejemplo` para comprobar.\n", encoding="utf-8"
    )
    return Brain(
        dict(
            scope=request.param,
            timezone="Europe/Madrid",
            vault_path=str(tmp_path / "vault"),
            state_path=str(tmp_path / "state"),
            documentation_roots={"demo": str(docs)},
        )
    )


def payload(**changes):
    return {
        "target": "documentation:demo:guide.md",
        "title": "Guía de ejemplo",
        "project": "demo",
        "tags": ["Comando", "ñandú"],
        "version": 0,
        **changes,
    }


def test_persistence_exact_query_versions_and_delete_retry(brain):
    store = Favorites(brain)
    assert store.query()["items"] == []
    assert not (brain.state / "favorites.json").exists()
    item = store.save(payload())
    assert item["version"] == 1 and item["tags"] == ["comando", "ñandú"]
    assert store.save(payload()) == item
    assert Favorites(brain).query()["items"][0]["id"] == item["id"]
    assert (
        store.query("echo", {"tags": ["COMANDO"], "project": "demo", "kind": "documentation"})[
            "total"
        ]
        == 1
    )
    assert store.query(filters={"tags": ["com"]})["total"] == 0
    assert store.query(filters={"project": None})["total"] == 0
    assert store.query(filters={"tags": []})["total"] == 0
    assert store.query(identity="f" * 32)["total"] == 0
    assert store.query(identity=item["id"])["items"][0]["content_id"] == item["target"]
    assert Viewer(brain).content(item["target"])["item"]["favorite"]["id"] == item["id"]
    with pytest.raises(Conflict):
        store.save(payload(title="Otra edición"))
    edited = store.save(payload(title="Otra edición", version=1))
    with pytest.raises(Conflict):
        store.remove(item["id"], 1)
    store.remove(item["id"], edited["version"])
    assert store.remove(item["id"], edited["version"])["removed"]
    assert not store.query()["items"]
    with pytest.raises(Conflict):
        store.save(payload())  # A delayed original add cannot resurrect a removed favorite.
    assert store.query(filters={"target": item["target"]})["removed_version"] == 3
    added = store.save(payload(version=3))
    assert added["id"] == item["id"] and added["version"] == 4
    with pytest.raises(Conflict):
        store.remove(item["id"], edited["version"])
    assert not brain.ledger()["notes"] and not brain.ledger()["events"]


def test_parallel_add_and_conflicting_edits(brain):
    store = Favorites(brain)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: Favorites(brain).save(payload()), range(8)))
    assert all(r == rows[0] for r in rows) and store.query()["total"] == 1

    def edit(title):
        try:
            return Favorites(brain).save(payload(title=title, version=1))["version"]
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["Primera edición", "Segunda edición"]))
    assert sorted(map(str, results)) == ["2", "conflict"]


def test_unavailable_reference_and_permission_revalidation(brain, tmp_path):
    store = Favorites(brain)
    item = store.save(payload())
    guide = tmp_path / "docs/guide.md"
    guide.rename(tmp_path / "docs/renamed.md")
    row = store.query(identity=item["id"])["items"][0]
    assert not row["available"] and row["excerpt"] == "" and row["content_id"] is None
    with pytest.raises(ValueError):
        store.save(payload())
    guide.write_text("# Guía\n\nRestaurada\n", encoding="utf-8")
    assert store.query()["items"][0]["available"]
    brain.config["documentation_roots"] = {}
    assert not store.query()["items"][0]["available"]
    store.remove(item["id"], 1)
    assert store.query()["total"] == 0


def test_excerpts_show_body_instead_of_frontmatter_or_journal_markers(brain, tmp_path):
    guide = tmp_path / "docs/guide.md"
    guide.write_text(
        "---\ntags: [example]\nproject: demo\n---\n# Guía\n\n<!-- event:demo -->\nComando: `echo ejemplo`\n",
        encoding="utf-8",
    )
    store = Favorites(brain)
    store.save(payload())
    row = store.query()["items"][0]
    assert row["excerpt"] == "Comando: `echo ejemplo`"
    assert store.query("echo ejemplo")["total"] == 1


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "file:///example",
        "https://user:pass@example.test/",
        "https://example.test/?token=private",
        "https://example.test/?api_key=private",
        "https://example.test/?X-Amz-Signature=private",
        "https://example.test/#access_token=private",
        "https://example.test/?%61pi-key=private",
        "https://example.test:bad/",
        "documentation:demo:../guide.md",
        "documentation:missing:guide.md",
        "note:other:example",
        "https://example.test/\\bad",
    ],
)
def test_reject_invalid_or_unapproved_destinations(brain, target):
    with pytest.raises(ValueError):
        Favorites(brain).save(payload(target=target))
    assert not (brain.state / "favorites.json").exists()


def test_web_is_reference_only_budgets_and_pagination(brain):
    store = Favorites(brain)
    for i in range(25):
        store.save(payload(target=f"https://example.test/guide/{i}", title="Enlace " + str(i)))
    offset, seen = 0, set()
    while True:
        page = store.query(max_chars=4000, offset=offset, order="title")
        assert len(json.dumps(page, ensure_ascii=False)) <= 4000
        assert 0 < len(page["items"]) <= 20
        for row in page["items"]:
            assert row["id"] not in seen
            seen.add(row["id"])
            assert row["excerpt"] == "" and row["content_id"] is None and row["kind"] == "web"
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert len(seen) == 25
    for kwargs in [
        {"offset": True},
        {"max_chars": 3999},
        {"filters": {"scope": "work"}},
        {"identity": "../bad"},
    ]:
        with pytest.raises(ValueError):
            store.query(**kwargs)


def test_empty_query_diagnostics_respect_response_budget(brain):
    brain.config["documentation_roots"] = {
        "missing-" + str(i): str(brain.state / ("absent-" + str(i))) for i in range(10)
    }
    result = Favorites(brain).query(max_chars=4000)
    assert result["error_count"] == 10 and len(result["errors"]) == 5
    assert result["diagnostics_truncated"]
    assert len(json.dumps(result, ensure_ascii=False)) <= 4000


def test_corrupt_scope_limits_and_atomic_failure(brain, monkeypatch):
    import second_brain.favorites as module

    store = Favorites(brain)
    store.save(payload())
    path = brain.state / "favorites.json"
    before = path.read_bytes()
    monkeypatch.setattr(
        module, "atomic_write", lambda *a: (_ for _ in ()).throw(OSError("interrupted"))
    )
    with pytest.raises(OSError):
        store.save(payload(version=1, title="Cambio"))
    assert path.read_bytes() == before
    data = json.loads(before)
    for broken in [
        {**data, "schema_version": 2},
        {**data, "scope": "other"},
        {**data, "items": [data["items"][0]] * 2},
    ]:
        with pytest.raises(ValueError):
            decode(json.dumps(broken))
    monkeypatch.setattr(module, "MAX_ITEMS", 1)
    with pytest.raises(ValueError):
        store.save(payload(target="https://example.test/second"))
    assert path.read_bytes() == before
    path.write_text(
        json.dumps({**data, "scope": "work" if brain.scope == "personal" else "personal"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        store.export()


def test_recovery_preserves_preferences_and_scope(brain, tmp_path):
    item = Favorites(brain).save(payload())
    source = tmp_path / "backup"
    backup(brain, source)
    restored = tmp_path / "restored"
    restore(source, restored)
    other = Brain(load_config(restored / "config.json"))
    assert other.status()["paused"]
    assert Favorites(other).export() == Favorites(brain).export()
    assert not Favorites(other).query()["items"][0]["available"]  # Approved roots are not inferred.
    raw = source / "state/favorites.json"
    raw.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        read_bundle(source)
    assert Favorites(brain).query()["items"][0]["id"] == item["id"]


def test_mcp_cli_and_viewer_parity_and_explicit_cli_apply(brain, tmp_path):
    store = Favorites(brain)
    item = store.save(payload())
    expected = store.query("echo", {"project": "demo"})

    async def scenario():
        async with Client(create_server(brain.config)) as client:
            assert "read_favorites" in {t.name for t in await client.list_tools()}
            actual = await client.call_tool(
                "read_favorites", {"query": "echo", "filters": {"project": "demo"}}
            )
            assert actual.data == expected

    asyncio.run(scenario())
    config = tmp_path / "config.json"
    config.write_text(json.dumps({**brain.config, "schema_version": 1}), encoding="utf-8")

    def cli(*args, value=None):
        run = subprocess.run(
            [sys.executable, "-m", "second_brain.cli", "--config", str(config), "favorites", *args],
            input=value,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=os.environ.copy(),
            timeout=15,
        )
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)

    assert cli("list", "echo", "--project", "demo") == expected
    assert (
        cli(
            "save",
            "--request-file",
            "-",
            value=json.dumps(payload(target="https://example.test/extra")),
        )["status"]
        == "preview"
    )
    assert store.query()["total"] == 1
    assert cli("remove", item["id"], "--version", "1")["status"] == "preview"
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            actual = json.load(urlopen(server.url + "api/favorites?query=echo&project=demo"))
            assert actual == expected
            data = json.dumps(payload(target="https://example.test/extra")).encode()
            for origin, expected_code in [("https://example.test", 403), (server.origin, 200)]:
                request = Request(
                    server.url + "api/favorites",
                    data=data,
                    headers={"Content-Type": "application/json", "Origin": origin},
                    method="POST",
                )
                if expected_code == 403:
                    with pytest.raises(HTTPError) as exc:
                        urlopen(request)
                    assert exc.value.code == 403
                else:
                    assert json.load(urlopen(request))["target"] == "https://example.test/extra"
            with pytest.raises(HTTPError):
                urlopen(server.url + "api/favorites?scope=other")
        finally:
            server.shutdown()
            thread.join(5)


def test_runtime_checks_favorites_reader_before_activation(tmp_path, monkeypatch):
    from second_brain import runtime

    root = tmp_path / "install"
    (root / "data/state").mkdir(parents=True)
    (root / "data/state/favorites.json").write_text("{}")

    def candidate(args):
        assert "-c" in args and "favorites" in args[args.index("-c") + 1]
        raise ValueError("Candidate has no favorites reader")

    monkeypatch.setattr(runtime, "command", candidate)
    with pytest.raises(ValueError, match="no favorites reader"):
        runtime.probe(root, "0.1.0a5")


def test_complete_recovery_keeps_notes_marks_journal_tasks_log_and_favorites(brain, tmp_path):
    from second_brain.agent_log import AgentLog
    from second_brain.task_pages import TaskPages
    from test_core import event
    from test_agent_log import action

    brain.capture(event(scope=brain.scope, project="demo", tags=["comando"]))
    tasks = TaskPages(brain)
    tasks.save(
        dict(
            key="DEMO-1234",
            title="Revisar ejemplo",
            body="echo ejemplo",
            status="open",
            project="demo",
            tags=[],
            links=[],
            version=0,
        )
    )
    viewer = Viewer(brain)
    content_id = f"note:{brain.scope}:git-version"
    content = viewer.content(content_id)
    quote = "git --version"
    start = content["text"].index(quote)
    viewer.annotations.save(
        content,
        dict(
            document_id=content_id,
            revision=content["revision"],
            start=start,
            end=start + len(quote),
            quote=quote,
            color="green",
            tags=["comando"],
        ),
    )
    log = AgentLog(brain)
    log.configure(True, 0)
    log.record(action(scope=brain.scope))
    favorite = Favorites(brain).save(payload(target=content_id))
    backup(brain, tmp_path / "all-backup")
    restore(tmp_path / "all-backup", tmp_path / "all-restored")
    other = Brain(load_config(tmp_path / "all-restored/config.json"))
    assert other.status()["paused"]
    assert other.ledger() == brain.ledger()
    assert other.read("git-version") == brain.read("git-version")
    assert [
        (p.relative_to(other.vault), p.read_bytes())
        for p in sorted((other.vault / "journal").rglob("*.md"))
    ] == [
        (p.relative_to(brain.vault), p.read_bytes())
        for p in sorted((brain.vault / "journal").rglob("*.md"))
    ]
    assert TaskPages(other).export() == tasks.export()
    assert AgentLog(other).export() == log.export()
    assert Favorites(other).export() == Favorites(brain).export()
    assert Favorites(other).query(identity=favorite["id"])["items"][0]["available"]
    assert Viewer(other).annotations.export() == viewer.annotations.export()
