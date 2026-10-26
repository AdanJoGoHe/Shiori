from pathlib import Path
import json
import threading
from urllib.request import urlopen

import pytest

from second_brain.viewer import ViewerServer
from test_viewer import viewer as viewer


def mark(viewer, quote, tags, color="green", document_id="documentation:docs:guide.md"):
    document = viewer.content(document_id)
    start = document["text"].index(quote)
    return viewer.save_annotation(
        {
            "document_id": document_id,
            "revision": document["revision"],
            "start": start,
            "end": start + len(quote),
            "quote": quote,
            "color": color,
            "tags": tags,
        }
    )


def seed(viewer):
    path = Path(viewer.catalog.brain.config["documentation_roots"]["docs"]) / "guide.md"
    path.write_text(
        "---\ntags: [comando]\nproject: demo\n---\n# Guía\n\nAntes 😀\n\n```sh\nprintf 'listo'\ngit --version\n```\n\nServidor 192.0.2.10 y ruta /srv/demo. Fin.\n",
        encoding="utf-8",
    )
    command = mark(viewer, "printf 'listo'\ngit --version", ["comando", "informacion-importante"])
    ip = mark(viewer, "192.0.2.10", ["direccion-ip"], "blue")
    route = mark(viewer, "/srv/demo", ["ruta"], "orange")
    return path, command, ip, route


def test_fragment_categories_exact_quotes_context_and_document_facets(viewer):
    _, command, ip, route = seed(viewer)
    for category, expected in [("comando", command), ("direccion-ip", ip), ("ruta", route)]:
        result = viewer.items({"view": ["fragments"], "category": [category]})
        assert result["total"] == 1
        row = result["items"][0]
        assert row["annotation"]["id"] == expected["id"]
        assert row["annotation"]["quote"] == expected["quote"]
        assert row["context_before"] and row["context_after"]
        assert row["annotation"]["anchor"]["status"] == "resolved"
    assert viewer.items({"view": ["fragments"], "q": ["direccion ip"]})["total"] == 1
    assert viewer.items({"view": ["fragments"], "q": ["Servidor"]})["total"] == 0
    assert (
        viewer.items(
            {
                "view": ["fragments"],
                "category": ["comando", "informacion-importante"],
                "project": ["demo"],
                "kind": ["documentation"],
                "tag": ["comando"],
                "color": ["green"],
            }
        )["total"]
        == 1
    )
    for extra in [
        {"project": ["other"]},
        {"color": ["blue"]},
        {"category": ["comando", "ruta"]},
        {"from": ["2999-01-01"]},
    ]:
        assert viewer.items({"view": ["fragments"], "category": ["comando"], **extra})["total"] == 0


def test_fragment_search_combines_purpose_quote_and_category_without_context(viewer):
    _, command, _, _ = seed(viewer)
    viewer.save_annotation(
        {
            "version": 1,
            "title": "Comprobar versión instalada 😀",
            "description": "Consultar herramientas en un entorno local.",
        },
        command["id"],
    )
    result = viewer.items({"view": ["fragments"], "q": ["VERSION herramientas COMANDO"]})
    assert result["total"] == 1
    assert result["items"][0]["annotation"]["quote"] == command["quote"]
    assert result["items"][0]["annotation"]["title"] == "Comprobar versión instalada 😀"
    assert viewer.items({"view": ["fragments"], "q": ["herramientas inexistente"]})["total"] == 0
    assert viewer.items({"q": ["herramientas"]})["total"] == 0


def test_fragment_unresolved_context_is_saved_and_read_only(viewer):
    path, command, _, _ = seed(viewer)
    path.write_text("# Cambiado\n\nYa no contiene el comando.\n", encoding="utf-8")
    roots = [path.parent, viewer.catalog.brain.vault, viewer.catalog.brain.state]
    before = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
    row = viewer.items({"view": ["fragments"], "category": ["comando"]})["items"][0]
    assert row["annotation"]["anchor"]["reason"] == "missing"
    assert row["annotation"]["quote"] == command["quote"]
    assert row["context_before"] == command["prefix"][-80:]
    assert before == {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}


def test_fragment_paging_untagged_archived_and_catalog_bounds(viewer, monkeypatch):
    seed(viewer)
    for _ in range(22):
        mark(viewer, "192.0.2.10", [])
    result = viewer.items({"view": ["fragments"], "category": ["__none__"]})
    second = viewer.items({"view": ["fragments"], "category": ["__none__"], "offset": ["20"]})
    assert result["total"] == 22 and result["next_offset"] == 20
    assert len(second["items"]) == 2 and second["next_offset"] is None
    assert len({r["annotation"]["id"] for r in result["items"] + second["items"]}) == 22
    viewer.annotations.save_category(
        {"label": "Comando", "color": "green", "archived": True, "version": 1}, "comando"
    )
    assert viewer.items({"view": ["fragments"], "category": ["comando"]})["total"] == 1
    original = viewer.catalog.snapshot
    monkeypatch.setattr(
        viewer.catalog,
        "snapshot",
        lambda *args: {**original(*args), "items": [], "truncated": True},
    )
    bounded = viewer.items({"view": ["fragments"]})
    assert bounded["total"] == 0 and bounded["truncated"]


@pytest.mark.parametrize(
    "extra",
    [{"view": ["bad"]}, {"category": ["../outside"]}, {"color": ["red"]}, {"category": ["x"] * 21}],
)
def test_invalid_fragment_filters(viewer, extra):
    with pytest.raises(ValueError):
        viewer.items({"view": ["fragments"], **extra})


def test_http_fragment_search_and_document_mode_unchanged(viewer):
    seed(viewer)
    assert viewer.items({"q": ["Servidor"]})["total"] == 1
    with ViewerServer(viewer.catalog.brain, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                server.url + "api/items?view=fragments&category=comando", timeout=5
            ) as response:
                data = json.loads(response.read())
                assert (
                    data["total"] == 1
                    and data["items"][0]["annotation"]["quote"] == "printf 'listo'\ngit --version"
                )
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_missing_document_retains_only_sidecar_text_and_never_reads_an_unknown_path(
    viewer, monkeypatch
):
    path, command, _, _ = seed(viewer)
    path.unlink()
    original = viewer.catalog.read
    reads = []

    def read(content_id, snapshot=None):
        reads.append(content_id)
        return original(content_id, snapshot)

    monkeypatch.setattr(viewer.catalog, "read", read)
    found = viewer.items({"view": ["fragments"], "category": ["comando"]})
    assert found["total"] == 1
    row = found["items"][0]
    assert row["available"] is False and row["metadata"] == {}
    assert row["annotation"]["quote"] == command["quote"]
    assert row["annotation"]["anchor"]["reason"] == "unavailable"
    assert command["document_id"] not in reads
    assert viewer.items({"view": ["fragments"], "project": ["demo"]})["total"] == 0
    assert viewer.items({"view": ["fragments"], "to": ["2999-01-01"]})["total"] == 0
    viewer.catalog.brain.config["documentation_roots"] = {}
    assert viewer.items({"view": ["fragments"]})["total"] == 0
