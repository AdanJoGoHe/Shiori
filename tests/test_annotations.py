import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from second_brain.annotations import Annotations, Conflict
from second_brain.viewer import ViewerServer
from test_viewer import viewer as viewer


def selection(viewer):
    document = viewer.content("documentation:docs:guide.md")
    quote = "Búsquedas locales"
    start = document["text"].index(quote)
    return {
        "document_id": document["item"]["id"],
        "revision": document["revision"],
        "start": start,
        "end": start + len(quote),
        "quote": quote,
        "color": "yellow",
        "tags": ["informacion-importante"],
    }


def test_round_trip_update_conflict_delete_restore_and_unchanged_sources(viewer):
    brain = viewer.catalog.brain
    ledger_before = brain.ledger_path.read_bytes()
    docs = Path(brain.config["documentation_roots"]["docs"])
    before = {
        p: p.read_bytes() for root in [brain.vault, docs] for p in root.rglob("*") if p.is_file()
    }
    payload = selection(viewer)
    item = viewer.save_annotation(payload)
    assert item["version"] == 1 and item["suffix"]
    assert Annotations(brain).export()["items"] == [item]
    listed = viewer.annotation_items(payload["document_id"])["items"][0]
    assert listed.pop("anchor")["reason"] == "current"
    assert listed == item
    edited = viewer.save_annotation({**payload, "color": "blue", "version": 1}, item["id"])
    assert edited["created_at"] == item["created_at"] and edited["version"] == 2
    with pytest.raises(Conflict):
        viewer.save_annotation({**payload, "version": 1}, item["id"])
    with pytest.raises(Conflict):
        viewer.annotations.delete(item["id"], 1)
    export = json.dumps(viewer.annotations.export())
    viewer.annotations.delete(item["id"], 2)
    assert not viewer.annotations.export()["items"]
    assert viewer.annotations.restore(export) == {"status": "restored", "count": 1}
    assert viewer.annotations.export()["items"] == [edited]
    assert before == {
        p: p.read_bytes() for root in [brain.vault, docs] for p in root.rglob("*") if p.is_file()
    }
    assert brain.ledger_path.read_bytes() == ledger_before


def test_details_edit_orphan_preserves_anchor_undo_and_old_caller_fields(viewer):
    payload = selection(viewer)
    item = viewer.save_annotation(
        {
            **payload,
            "title": "Consultar conexión 😀",
            "description": "Sirve para revisar una consulta local.",
        }
    )
    # Existing clients can still edit selection/color without erasing the new fields.
    updated = viewer.save_annotation({**payload, "version": 1}, item["id"])
    assert updated["title"] == item["title"] and updated["description"] == item["description"]
    path = Path(viewer.catalog.brain.config["documentation_roots"]["docs"]) / "guide.md"
    path.unlink()
    before = viewer.catalog.brain.ledger_path.read_bytes()
    details = {"version": 2, "title": "Red local", "description": "Buscar por propósito."}
    edited = viewer.save_annotation(details, item["id"])
    for key in item.keys() - {"version", "updated_at", "title", "description"}:
        assert edited[key] == item[key]
    assert viewer.items({"view": ["fragments"], "q": ["RED proposito"]})["total"] == 1
    with pytest.raises(Conflict):
        viewer.save_annotation(details, item["id"])
    deleted = viewer.delete_annotation(item["id"], 3)
    restored = viewer.undo_annotation({"token": deleted["undo_token"]})
    assert restored["title"] == edited["title"] and restored["description"] == edited["description"]
    exported = viewer.annotations.export()
    viewer.annotations.restore(json.dumps(exported))
    assert viewer.annotations.export() == exported
    cleared = viewer.save_annotation(
        {"version": restored["version"], "title": "", "description": ""}, item["id"]
    )
    assert cleared["title"] == cleared["description"] == ""
    assert viewer.catalog.brain.ledger_path.read_bytes() == before
    assert not path.exists()


@pytest.mark.parametrize(
    "metadata",
    [
        {"title": "x" * 121},
        {"description": "x" * 1001},
        {"title": None},
        {"description": []},
        {"description": "password=synthetic-test-secret"},
    ],
)
def test_invalid_details_preserve_store(viewer, metadata):
    item = viewer.save_annotation(selection(viewer))
    path = viewer.catalog.brain.state / "annotations.json"
    before = path.read_bytes()
    details = {"title": "", "description": "", **metadata}
    with pytest.raises(ValueError):
        viewer.save_annotation({**selection(viewer), **details})
    with pytest.raises(ValueError):
        viewer.save_annotation({"version": 1, **details}, item["id"])
    assert path.read_bytes() == before


def test_schema_two_adoption_is_read_only_and_first_write_preserves_exact_prior(viewer):
    item = viewer.save_annotation(selection(viewer))
    store = viewer.annotations
    legacy = {
        **store.export(),
        "schema_version": 2,
        "items": [{k: v for k, v in item.items() if k not in {"title", "description"}}],
    }
    raw = json.dumps(legacy, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode("utf-8")
    path = store.brain.state / "annotations.json"
    path.write_bytes(raw)
    exported = store.export()
    assert exported["schema_version"] == 3
    assert exported["items"] == [item]
    assert path.read_bytes() == raw
    store.save_details(item["id"], {"version": 1, "title": "Nombre útil", "description": ""})
    assert (path.parent / "annotations.previous.json").read_bytes() == raw
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 3
    # Legacy schema cannot smuggle fields that were not part of its contract.
    with pytest.raises(ValueError):
        store.restore(json.dumps({**legacy, "items": [item]}))


@pytest.mark.parametrize(
    "change",
    [
        {"color": "javascript:bad"},
        {"tags": ["../../bad"]},
        {"tags": ["a", "a"]},
        {"start": True},
        {"end": 999999},
        {"quote": "different"},
        {"extra": "bad"},
        {"document_id": "documentation:docs:../private.md"},
        {"revision": "0" * 64},
    ],
)
def test_untrusted_selection_rejected(viewer, change):
    with pytest.raises(ValueError):
        viewer.save_annotation({**selection(viewer), **change})
    assert not viewer.annotations.export()["items"]


def test_changed_source_requires_reload_and_code_unicode_contract(viewer):
    payload = selection(viewer)
    docs = Path(viewer.catalog.brain.config["documentation_roots"]["docs"])
    (docs / "guide.md").write_text(
        "# Changed\n\nBúsquedas locales\n\n```sh\necho 😀\n```\n", encoding="utf-8"
    )
    with pytest.raises(Conflict):
        viewer.save_annotation(payload)
    document = viewer.content(payload["document_id"])
    quote = "echo 😀"
    start = document["text"].index(quote)
    item = viewer.save_annotation(
        {
            **payload,
            "revision": document["revision"],
            "quote": quote,
            "start": start,
            "end": start + len(quote),
        }
    )
    assert item["quote"] == quote and item["end"] - item["start"] == 6


def test_concurrent_edits_do_not_overwrite(viewer):
    payload = selection(viewer)
    item = viewer.save_annotation(payload)

    def update(color):
        try:
            return viewer.save_annotation({**payload, "color": color, "version": 1}, item["id"])[
                "version"
            ]
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ["blue", "pink"]))
    assert sorted(map(str, results)) == ["2", "conflict"]


def test_store_bounds_and_invalid_import_preserve_collection(viewer, monkeypatch):
    import second_brain.annotations as module

    first = viewer.save_annotation(selection(viewer))
    monkeypatch.setattr(module, "MAX_ITEMS", 1)
    with pytest.raises(ValueError):
        viewer.save_annotation(selection(viewer))
    assert viewer.annotations.export()["items"] == [first]
    bad = {**first, "tags": ["not a category id"]}
    with pytest.raises(ValueError):
        viewer.annotations.restore(json.dumps({"schema_version": 1, "items": [bad]}))
    with pytest.raises(ValueError):
        viewer.annotations.restore("[" * 2000 + "]" * 2000)
    assert viewer.annotations.export()["items"] == [first]


def test_interrupted_commit_and_corrupt_store_recovery(viewer, monkeypatch):
    import second_brain.annotations as module

    payload = selection(viewer)
    first = viewer.save_annotation(payload)
    path = viewer.catalog.brain.state / "annotations.json"
    before = path.read_bytes()
    real_write = module.atomic_write

    def fail_commit(target, content):
        if target.name == "annotations.json":
            raise OSError("synthetic interrupted commit")
        real_write(target, content)

    monkeypatch.setattr(module, "atomic_write", fail_commit)
    with pytest.raises(OSError):
        viewer.save_annotation({**payload, "version": 1, "color": "pink"}, first["id"])
    assert path.read_bytes() == before
    backup = (path.parent / "annotations.previous.json").read_bytes()
    assert json.loads(backup)["items"] == [first]
    monkeypatch.setattr(module, "atomic_write", real_write)
    path.write_text('{"broken":', encoding="utf-8")
    with pytest.raises(ValueError):
        viewer.save_annotation(payload)
    viewer.annotations.restore(backup.decode("utf-8"))
    assert viewer.annotations.export()["items"] == [first]
    assert (path.parent / "annotations.previous.json").read_bytes() == backup
    with pytest.raises(ValueError):
        viewer.annotations.restore('{"schema_version":9,"items":[]}')
    assert viewer.annotations.export()["items"] == [first]


def test_http_annotation_crud_and_write_boundary(viewer):
    with ViewerServer(viewer.catalog.brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = server.url + "api/annotations"
        payload = selection(viewer)

        def send(method, data, target=url, headers=None):
            request = Request(
                target,
                method=method,
                data=json.dumps(data).encode(),
                headers=headers
                if headers is not None
                else {"Origin": server.origin, "Content-Type": "application/json"},
            )
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())

        try:
            for headers in [
                {"Content-Type": "application/json"},
                {"Content-Type": "application/json", "Origin": "https://attacker.test"},
                {"Content-Type": "text/plain", "Origin": server.origin},
                {
                    "Content-Type": "application/json",
                    "Origin": server.origin,
                    "Host": "attacker.test",
                },
                {
                    "Content-Type": "application/json",
                    "Origin": server.origin,
                    "Sec-Fetch-Site": "same-site",
                },
            ]:
                with pytest.raises(HTTPError) as error:
                    send("POST", payload, headers=headers)
                assert error.value.code in (400, 403)
            with pytest.raises(HTTPError) as error:
                send("POST", payload, server.origin + "/api/annotations")
            assert error.value.code == 405
            status, item = send("POST", payload)
            assert status == 201
            with urlopen(
                url + "?" + urlencode({"document_id": payload["document_id"]}), timeout=5
            ) as response:
                listed = json.loads(response.read())["items"][0]
                assert listed.pop("anchor")["reason"] == "current"
                assert listed == item
            target = url + "?" + urlencode({"id": item["id"]})
            _, updated = send("PATCH", {**payload, "version": 1, "color": "blue"}, target)
            assert updated["version"] == 2
            with pytest.raises(HTTPError) as error:
                send("PATCH", {**payload, "version": 1}, target)
            assert error.value.code == 409
            docs = Path(viewer.catalog.brain.config["documentation_roots"]["docs"])
            (docs / "guide.md").unlink()
            with urlopen(
                url + "?" + urlencode({"document_id": payload["document_id"]}), timeout=5
            ) as response:
                orphan = json.loads(response.read())["items"][0]
                assert orphan["quote"] == payload["quote"]
                assert orphan["anchor"]["reason"] == "unavailable"
                assert orphan["anchor"]["start"] is None
            details = {"version": 2, "title": "Consultar red", "description": "Propósito local"}
            with pytest.raises(HTTPError) as error:
                send("PATCH", details, target, headers={"Content-Type": "application/json"})
            assert error.value.code == 403
            saved = send("PATCH", details, target)[1]
            assert saved["version"] == 3 and saved["title"] == details["title"]
            assert saved["quote"] == payload["quote"] and saved["start"] == payload["start"]
            with pytest.raises(HTTPError) as error:
                send("PATCH", details, target)
            assert error.value.code == 409
            deleted = send("DELETE", {"version": 3}, target)[1]
            assert deleted["status"] == "deleted"
            assert not viewer.annotations.export()["items"]
            undo_url = server.url + "api/annotations/undo"
            with pytest.raises(HTTPError) as error:
                send(
                    "POST",
                    {"token": deleted["undo_token"]},
                    undo_url,
                    headers={"Content-Type": "application/json"},
                )
            assert error.value.code == 403
            restored = send("POST", {"token": deleted["undo_token"]}, undo_url)[1]
            assert restored["id"] == item["id"] and restored["version"] == 4
            assert restored["title"] == details["title"]
            with pytest.raises(HTTPError) as error:
                send("POST", {"token": deleted["undo_token"]}, undo_url)
            assert error.value.code == 409
            assert send("DELETE", {"version": 4}, target)[1]["status"] == "deleted"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_cli_export_restore_does_not_overwrite_export(viewer, tmp_path, monkeypatch, capsys):
    import sys
    from second_brain.cli import main

    viewer.save_annotation(selection(viewer))
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({**viewer.catalog.brain.config, "schema_version": 1}), encoding="utf-8"
    )
    export = tmp_path / "export.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["second-brain", "--config", str(config), "annotations-export", "--output", str(export)],
    )
    main()
    assert json.loads(capsys.readouterr().out)["status"] == "exported"
    with pytest.raises(SystemExit):
        main()
    assert len(json.loads(export.read_text(encoding="utf-8"))["items"]) == 1
    monkeypatch.setattr(
        sys,
        "argv",
        ["second-brain", "--config", str(config), "annotations-restore", "--input", str(export)],
    )
    main()
    assert json.loads(capsys.readouterr().out)["count"] == 1
