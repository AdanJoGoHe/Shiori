import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain.annotations import Conflict
from second_brain.backup import backup, restore
from second_brain.catalog import Catalog
from second_brain.core import Brain, load_config
from second_brain.server import create_server
from second_brain.task_pages import TaskPages
from second_brain.viewer import Viewer


def payload(**changes):
    return dict(
        key="DEMO-1234",
        title="Consultar el ejemplo",
        body="## Comprobar\n\n`echo demo`",
        status="open",
        project="demo",
        tags=["Ejemplo"],
        links=[],
        version=0,
        **changes,
    )


@pytest.fixture(params=["personal", "work"])
def brain(tmp_path, request):
    return Brain(
        dict(
            scope=request.param,
            timezone="Europe/Madrid",
            vault_path=str(tmp_path / "vault"),
            state_path=str(tmp_path / "state"),
        )
    )


def test_task_persistence_conflict_and_catalog(brain):
    store = TaskPages(brain)
    value = payload()
    item = store.save(value)
    assert item["version"] == 1 and item["tags"] == ["ejemplo"]
    assert store.save(value) == item
    assert TaskPages(brain).read("demo-1234") == item
    with pytest.raises(Conflict):
        store.save({**value, "title": "Edición antigua"})
    updated = store.save({**value, "body": "Nuevo contexto", "version": 1})
    assert updated["version"] == 2
    assert store.read("DEMO-1234")["body"] == "Nuevo contexto"
    content_id = f"task:{brain.scope}:DEMO-1234"
    assert Catalog(brain).list("task")["items"][0]["id"] == content_id
    viewer = Viewer(brain)
    assert viewer.items({"q": ["demo-1234"], "kind": ["task"]})["total"] == 1
    content = viewer.content(content_id)
    mark = viewer.annotations.save(
        content,
        dict(
            document_id=content_id,
            revision=content["revision"],
            start=0,
            end=5,
            quote="Nuevo",
            color="green",
            tags=["informacion-importante"],
        ),
    )
    assert (
        viewer.items({"view": ["fragments"], "kind": ["task"]})["items"][0]["annotation"]["id"]
        == mark["id"]
    )
    assert brain.ledger()["notes"] == {}  # A task is not verified knowledge.


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "file:///private",
        "https://user:pass@example.test/",
        "https://example.test/?token=hidden",
        "note:personal:../private",
        "https://example.test/\\bad",
    ],
)
def test_task_rejects_dangerous_links(brain, target):
    with pytest.raises(ValueError):
        TaskPages(brain).save(
            {**payload(), "links": [dict(target=target, label="Ejemplo", annotation_id=None)]}
        )
    assert not (brain.state / "task-pages.json").exists()


def test_task_backup_restores_marks_and_links(brain, tmp_path):
    store = TaskPages(brain)
    value = {
        **payload(),
        "links": [
            dict(
                target="https://example.test/issue/DEMO-1234",
                annotation_id=None,
                label="Incidencia de ejemplo",
            )
        ],
    }
    store.save(value)
    viewer = Viewer(brain)
    content = viewer.content(f"task:{brain.scope}:DEMO-1234")
    start = content["text"].index("echo demo")
    viewer.annotations.save(
        content,
        dict(
            document_id=content["item"]["id"],
            revision=content["revision"],
            start=start,
            end=start + 9,
            quote="echo demo",
            color="green",
            tags=["comando"],
        ),
    )
    backup(brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    recovered = Brain(load_config(tmp_path / "restored" / "config.json"))
    assert TaskPages(recovered).export() == store.export()
    assert Viewer(recovered).annotations.export() == viewer.annotations.export()
    assert recovered.status()["paused"]


def test_task_corruption_and_scope_are_never_overwritten(brain):
    store = TaskPages(brain)
    store.save(payload())
    path = brain.state / "task-pages.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["scope"] = "work" if brain.scope == "personal" else "personal"
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store.save({**payload(), "version": 1, "body": "Cambios"})
    assert path.read_bytes() == before


def test_task_http_checks_origin_scope_links_and_conflicts(brain, tmp_path):
    import threading
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from second_brain.viewer import ViewerServer

    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "guide.md"
    source.write_text("# Documento ficticio\n\nContexto", encoding="utf-8")
    brain.config["documentation_roots"] = {"demo": str(docs)}
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:

            def post(value, origin=None):
                request = Request(
                    server.url + "api/tasks",
                    data=json.dumps(value).encode(),
                    headers={"Origin": origin or server.origin, "Content-Type": "application/json"},
                )
                with urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            with pytest.raises(HTTPError) as denied:
                post(payload(), "https://attacker.test")
            assert denied.value.code == 403
            assert not (brain.state / "task-pages.json").exists()
            assert post(payload())["version"] == 1
            with pytest.raises(HTTPError) as conflict:
                post({**payload(), "body": "Edición antigua"})
            assert conflict.value.code == 409
            for target in ["note:work:missing", "documentation:demo:../private.md"]:
                with pytest.raises(HTTPError) as invalid:
                    post(
                        {
                            **payload(),
                            "version": 1,
                            "links": [dict(target=target, annotation_id=None, label="Referencia")],
                        }
                    )
                assert invalid.value.code == 400
            link = dict(target="documentation:demo:guide.md", annotation_id=None, label="Guía")
            post({**payload(), "version": 1, "links": [link]})
            with urlopen(server.url + "api/tasks?key=demo-1234", timeout=5) as response:
                assert json.loads(response.read())["links"][0]["available"]
            source.unlink()
            with urlopen(server.url + "api/tasks?key=DEMO-1234", timeout=5) as response:
                assert not json.loads(response.read())["links"][0]["available"]
            post(
                {
                    **payload(),
                    "version": 2,
                    "links": [link],
                    "title": "Referencia ausente conservada",
                }
            )
        finally:
            server.shutdown()
            thread.join(5)


def test_task_cli_read_and_list_do_not_expose_other_scope(brain, tmp_path):
    import os
    import subprocess
    import sys

    TaskPages(brain).save(payload())
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema_version": 1, **brain.config}), encoding="utf-8")
    command = [sys.executable, "-m", "second_brain.cli", "--config", str(config), "task"]
    process = subprocess.run(
        command + ["read", "demo-1234", "--format", "text"],
        capture_output=True,
        text=True,
        env=os.environ,
    )
    assert process.returncode == 0
    assert "echo demo" in process.stdout and "DEMO-1234" in process.stdout
    process = subprocess.run(command + ["list"], capture_output=True, text=True, env=os.environ)
    assert process.returncode == 0
    assert json.loads(process.stdout)["items"][0]["source"] == brain.scope


def test_runtime_rejects_candidate_without_task_support(brain, tmp_path, monkeypatch):
    from second_brain import runtime

    root = tmp_path / "installation"
    data = root / "data" / "state"
    data.mkdir(parents=True)
    (data / "task-pages.json").write_text(json.dumps(TaskPages(brain).export()), encoding="utf-8")

    def candidate(arguments):
        if "-c" in arguments:
            raise ValueError("Candidate has no task storage reader")
        pytest.fail("Incompatible candidate must not reach the normal probe")

    monkeypatch.setattr(runtime, "command", candidate)
    with pytest.raises(ValueError, match="no task storage reader"):
        runtime.probe(root, "0.1.0a5")


def test_task_catalog_snapshot_stays_consistent_and_metadata_excludes_bodies(brain):
    store = TaskPages(brain)
    store.save(payload())
    catalog = Catalog(brain)
    snapshot = catalog.snapshot("task")
    content_id = snapshot["items"][0]["id"]
    store.save({**payload(), "version": 1, "title": "Título nuevo", "body": "Contexto nuevo"})
    row, old_body = catalog.read(content_id, snapshot)
    assert row["title"].endswith("Consultar el ejemplo")
    assert "echo demo" in old_body and "Contexto nuevo" not in old_body
    assert "Contexto nuevo" in catalog.read(content_id)[1]
    assert "Contexto nuevo" not in json.dumps(catalog.list("task"))


def test_task_mcp_partial_edit_replay_and_pause(brain):
    store = TaskPages(brain)
    store.save(payload())

    async def exercise():
        async with Client(create_server(brain.config)) as client:

            async def call(tool, **args):
                return (await client.call_tool(tool, args)).data

            key = "demo-1234"
            request = dict(issue_key=key, expected_version=1, changes={"status": "blocked"})
            assert (await call("get_task_page", issue_key=key))["version"] == 1
            first = await call("save_task_page", **request, event_id="demo-update")
            assert (first["status"], first["version"]) == ("saved", 2)
            page = store.read(key)
            assert page["project"] == "demo" and page["body"] == payload()["body"]
            assert page["tags"] == ["ejemplo"]
            latest = store.save(
                {**payload(), "title": "New title", "status": "blocked", "version": 2}
            )
            assert latest["version"] == 3

            brain.pause(True)
            retry = await call("save_task_page", **request, event_id="demo-update")
            assert (retry["status"], retry["version"]) == ("duplicate", 2)
            rejected = await call(
                "save_task_page",
                **{**request, "changes": {"status": "done"}},
                event_id="demo-update",
            )
            assert rejected["reason"] == "event-id-reused"
            blocked = await call("save_task_page", **request, event_id="paused-edit")
            assert blocked["reason"] == "paused"
            brain.pause(False)

            stale = await call("save_task_page", **request, event_id="stale-edit")
            assert (stale["reason"], stale["version"]) == ("version-mismatch", 3)
            unchanged = await call(
                "save_task_page", **{**request, "expected_version": 3}, event_id="same-content"
            )
            assert (unchanged["status"], unchanged["version"]) == ("unchanged", 3)
            result = await call(
                "list_task_pages",
                filters={"project": "demo", "tags": ["EJEMPLO"], "status": "blocked"},
            )
            assert result["scope"] == brain.scope and result["total"] == 1
            assert result["items"][0]["version"] == 3
            assert not {"body", "links"} & set(result["items"][0])
            with pytest.raises(ToolError):
                await call("get_task_page", issue_key="DEMO-123")
            with pytest.raises(ToolError):
                await call(
                    "save_task_page", **{**request, "expected_version": True}, event_id="invalid"
                )
            assert store.read(key) == latest
            assert brain.ledger() == {"events": {}, "notes": {}}

    asyncio.run(exercise())


def test_task_agent_links_use_local_catalog_and_preserve_unavailable_links(brain, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    guide = docs / "guide.md"
    guide.write_text("# Fictional guide\n\n`echo demo`", encoding="utf-8")
    brain.config["documentation_roots"] = {"demo": str(docs)}
    store = TaskPages(brain)
    linked = store.save(payload())
    content_id = "documentation:demo:guide.md"
    viewer = Viewer(brain)
    content = viewer.content(content_id)
    start = content["text"].index("echo demo")
    mark = viewer.annotations.save(
        content,
        dict(
            document_id=content_id,
            revision=content["revision"],
            start=start,
            end=start + 9,
            quote="echo demo",
            color="green",
            tags=["comando"],
        ),
    )
    link = dict(target=content_id, label="Demo fragment", annotation_id=mark["id"])
    for denied in [
        {**link, "target": f"task:{brain.scope}:{linked['key']}"},
        {**link, "target": "note:other:missing", "annotation_id": None},
        {**link, "target": "https://example.test/?token=hidden", "annotation_id": None},
    ]:
        with pytest.raises(ValueError):
            store.edit("DEMO-2", 0, {"title": "Second task", "links": [denied]}, "demo-create")
    task_link = dict(
        target=f"task:{brain.scope}:{linked['key']}", label="Related task", annotation_id=None
    )
    changes = {"title": "Second task", "links": [link, task_link]}
    assert store.edit("DEMO-2", 0, changes, "demo-create")["status"] == "saved"
    guide.unlink()
    assert store.edit("DEMO-2", 0, changes, "demo-create")["status"] == "duplicate"
    assert store.edit("DEMO-2", 1, {"status": "done"}, "demo-done")["version"] == 2
    assert store.read("DEMO-2")["links"] == [link, task_link]


def test_task_events_survive_concurrent_edits_failed_write_and_restore(
    brain, tmp_path, monkeypatch
):
    from second_brain import task_pages

    store = TaskPages(brain)
    changes = {"title": "Fictional issue"}
    write = task_pages.atomic_write

    def fail(*_):
        raise OSError("simulated write failure")

    with monkeypatch.context() as patch:
        patch.setattr(task_pages, "atomic_write", fail)
        with pytest.raises(OSError):
            store.edit("DEMO-1", 0, changes, "demo-create")
    assert not (brain.state / "task-pages.json").exists()
    assert task_pages.atomic_write == write
    assert store.edit("DEMO-1", 0, changes, "demo-create")["version"] == 1

    def edit(status):
        return TaskPages(brain).edit("DEMO-1", 1, {"status": status}, f"demo-{status}")

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(edit, ["blocked", "done"]))
    assert sorted(result["status"] for result in outcomes) == ["conflict", "saved"]
    assert store.read("DEMO-1")["version"] == 2
    backup(brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    recovered = TaskPages(Brain(load_config(tmp_path / "restored" / "config.json")))
    assert recovered.export() == store.export()
    assert recovered.edit("DEMO-1", 0, changes, "demo-create")["version"] == 1


def test_task_list_metadata_pagination(brain):
    store = TaskPages(brain)
    for index in range(21):
        store.save({**payload(), "key": f"DEMO-{index:02d}", "tags": []})
    first = store.list({"tags": []})
    assert first["total"] == 21 and first["next_offset"] == 20
    second = store.list({"tags": []}, first["next_offset"])
    assert [row["key"] for row in second["items"]] == ["DEMO-20"]
    assert second["next_offset"] is None
    assert store.list({"project": None})["total"] == 0
