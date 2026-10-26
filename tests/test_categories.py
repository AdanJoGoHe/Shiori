import json
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from second_brain.annotations import Annotations, Conflict, decode
from second_brain.viewer import ViewerServer
from test_annotations import selection
from test_viewer import viewer as viewer


def edit(row, **changes):
    return {key: changes.get(key, row[key]) for key in ("label", "color", "archived", "version")}


def test_seed_create_rename_recolor_archive_restore_and_references(viewer):
    store = viewer.annotations
    ledger_before = store.brain.ledger_path.read_bytes()
    note_before = store.brain.read("git")
    assert [r["label"] for r in store.categories()["items"]] == [
        "Comando",
        "Información importante",
        "Dirección IP",
        "URL",
        "Ruta",
    ]
    assert not (store.brain.state / "annotations.json").exists()
    category = store.save_category({"label": "  Mi\t categoría  ", "color": "pink"})
    assert category["label"] == "Mi categoría"
    payload = {**selection(viewer), "tags": ["comando", category["id"]], "color": "blue"}
    mark = viewer.save_annotation(payload)
    before = store.export()["items"]
    category = store.save_category(
        edit(category, label="Nueva categoría", color="violet"), category["id"]
    )
    assert category["version"] == 2
    assert store.export()["items"] == before
    assert next(r for r in store.categories()["items"] if r["id"] == category["id"])["uses"] == 1
    category = store.save_category(edit(category, archived=True), category["id"])
    assert store.export()["items"] == before
    with pytest.raises(ValueError):
        viewer.save_annotation(payload)
    # Retaining an archived reference while editing a mark remains valid.
    viewer.save_annotation({**payload, "version": 1, "color": "orange"}, mark["id"])
    category = store.save_category(edit(category, archived=False), category["id"])
    viewer.save_annotation(payload)
    bundle = store.export()
    store.save_category(edit(category, label="Changed"), category["id"])
    store.restore(json.dumps(bundle))
    assert Annotations(store.brain).export() == bundle
    assert store.brain.ledger_path.read_bytes() == ledger_before
    assert store.brain.read("git") == note_before


@pytest.mark.parametrize(
    "label",
    [
        "comando",
        "  COMANDO  ",
        "ＣＯＭＡＮＤＯ",
        "informacion importante",
        "Información   importante",
    ],
)
def test_duplicate_names_normalized_before_commit(viewer, label):
    before = viewer.annotations.export()
    with pytest.raises(ValueError):
        viewer.annotations.save_category({"label": label, "color": "blue"})
    assert viewer.annotations.export() == before
    assert not (viewer.catalog.brain.state / "annotations.json").exists()


def test_invalid_categories_and_stale_edits_preserve_previous_bytes(viewer, monkeypatch):
    store = viewer.annotations
    row = store.save_category({"label": "Custom", "color": "pink"})
    path = store.brain.state / "annotations.json"
    before = path.read_bytes()
    for payload in [
        {"label": "", "color": "blue"},
        {"label": "x" * 101, "color": "blue"},
        {"label": "Name", "color": []},
        {"label": "Name", "color": "#ffffff"},
        {"label": "Name", "color": "pink", "id": "../escape"},
    ]:
        with pytest.raises(ValueError):
            store.save_category(payload)
        assert path.read_bytes() == before
    for changes in [{"version": True}, {"archived": 1}, {"color": "bad"}]:
        with pytest.raises(ValueError):
            store.save_category(edit(row, **changes), row["id"])
    with pytest.raises(ValueError):
        store.save_category(edit(row), "not-present")
    store.save_category(edit(row, label="Updated"), row["id"])
    with pytest.raises(Conflict):
        store.save_category(edit(row, label="Lost edit"), row["id"])
    import second_brain.annotations as module

    monkeypatch.setattr(module, "MAX_CATEGORIES", 6)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store.save_category({"label": "Over the limit", "color": "blue"})
    assert path.read_bytes() == before


def test_concurrent_category_updates_use_same_store_lock(viewer):
    store = viewer.annotations
    row = store.save_category({"label": "Custom", "color": "pink"})

    def update(color):
        try:
            return store.save_category(edit(row, color=color), row["id"])["version"]
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(map(str, pool.map(update, ["blue", "green"]))) == ["2", "conflict"]


def test_legacy_migration_is_read_only_and_imports_preserve_unknown_tags(viewer):
    store = viewer.annotations
    mark = viewer.save_annotation(selection(viewer))
    legacy_mark = {k: v for k, v in mark.items() if k not in {"title", "description"}}
    legacy = {"schema_version": 1, "items": [{**legacy_mark, "tags": ["legacy-category"]}]}
    path = store.brain.state / "annotations.json"
    raw = json.dumps(legacy, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    path.write_bytes(raw.encode("utf-8"))
    migrated = store.export()
    assert migrated["schema_version"] == 3
    row = next(r for r in migrated["categories"] if r["id"] == "legacy-category")
    expected = [{**legacy["items"][0], "title": "", "description": ""}]
    assert row["label"] == "legacy-category" and migrated["items"] == expected
    assert path.read_bytes() == raw.encode("utf-8")
    store.save_category(edit(row, label="Legacy label"), row["id"])
    assert store.export()["items"] == expected
    assert (path.parent / "annotations.previous.json").read_bytes() == raw.encode("utf-8")
    exported = store.export()
    with pytest.raises(ValueError):
        store.restore(json.dumps({**exported, "categories": []}))
    assert store.export() == exported
    assert decode(raw)["items"] == expected


def test_unknown_new_tags_and_archived_duplicate_name_are_rejected(viewer):
    store = viewer.annotations
    with pytest.raises(ValueError):
        viewer.save_annotation({**selection(viewer), "tags": ["unknown"]})
    category = store.categories()["items"][0]
    store.save_category(edit(category, archived=True), category["id"])
    with pytest.raises(ValueError):
        store.save_category({"label": "COMANDO", "color": "blue"})
    assert not store.export()["items"]


def test_http_categories_guarded_crud_and_source_unchanged(viewer):
    brain = viewer.catalog.brain
    from pathlib import Path

    roots = [brain.vault, Path(brain.config["documentation_roots"]["docs"])]
    before = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
    opener = build_opener(ProxyHandler({}))
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(
            method, payload=None, url=None, origin=server.origin, content_type="application/json"
        ):
            headers = {"Content-Type": content_type}
            if origin is not None:
                headers["Origin"] = origin
            req = Request(
                url or server.url + "api/categories",
                method=method,
                headers=headers,
                data=None if payload is None else json.dumps(payload).encode(),
            )
            with opener.open(req, timeout=5) as response:
                return response.status, json.loads(response.read())

        try:
            assert len(request("GET")[1]["items"]) == 5
            payload = {"label": "Custom", "color": "blue"}
            for origin, content in [
                (None, "application/json"),
                ("https://attacker.test", "application/json"),
                (server.origin, "text/plain"),
            ]:
                with pytest.raises(HTTPError) as error:
                    request("POST", payload, origin=origin, content_type=content)
                assert error.value.code in {400, 403}
            with pytest.raises(HTTPError) as error:
                request("POST", payload, server.origin + "/api/categories")
            assert error.value.code == 405
            status, row = request("POST", payload)
            assert status == 201
            target = server.url + "api/categories?id=" + row["id"]
            _, archived = request("PATCH", edit(row, archived=True), target)
            assert archived["archived"] and archived["version"] == 2
            with pytest.raises(HTTPError) as error:
                request("PATCH", edit(row), target)
            assert error.value.code == 409
            with pytest.raises(HTTPError) as error:
                request("DELETE", {"version": 2}, target)
            assert error.value.code == 405
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert before == {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
