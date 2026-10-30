import json
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from second_brain.core import Brain
from second_brain.viewer import Viewer, ViewerServer


@pytest.fixture
def viewer(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "---\ntags: [python]\nproject: demo\n---\n# Guía de Python\n\nBúsquedas locales y UTF-8.\n\n## Instalación\n\n| Paso | Acción |\n|---|---|\n| 1 | Leer |\n",
        encoding="utf-8",
    )
    (docs / "index.md").write_text(
        "# Índice\n\n[Abrir guía](guide.md)\n[Fuera](../private.md)\n[Web](https://example.test)",
        encoding="utf-8",
    )
    (docs / "hostile.md").write_text(
        '# Contenido no confiable\n\n<script>alert(1)</script>\n<img src="https://example.test/a" onerror="alert(1)">\n\n![Remota](https://example.test/image)\n\n[Ejecutar](javascript:alert(1))',
        encoding="utf-8",
    )
    (docs / "credentials.md").write_text("Do not expose", encoding="utf-8")
    brain = Brain(
        {
            "scope": "personal",
            "vault_path": str(tmp_path / "vault"),
            "state_path": str(tmp_path / "state"),
            "timezone": "Europe/Madrid",
            "documentation_roots": {"docs": str(docs)},
        }
    )
    brain.capture(
        {
            "scope": "personal",
            "id": "git",
            "event_id": "git-event",
            "title": "Versión de Git",
            "type": "command",
            "status": "verified",
            "source_agent": "codex",
            "body": "git --version",
            "evidence": "Synthetic execution",
            "tags": ["python", "windows"],
            "project": "demo",
        }
    )
    return Viewer(brain)


def test_viewer_accent_search_and_combined_filters(viewer):
    found = viewer.items(
        {"q": ["busquedas"], "kind": ["documentation"], "tag": ["python"], "project": ["demo"]}
    )
    assert found["total"] == 1 and found["items"][0]["title"] == "Guía de Python"
    notes = viewer.items(
        {
            "kind": ["note"],
            "tag": ["python", "windows"],
            "status": ["verified"],
            "type": ["command"],
            "source_agent": ["codex"],
        }
    )
    assert notes["total"] == 1 and notes["items"][0]["title"] == "Versión de Git"
    assert viewer.items({"kind": ["documentation"], "status": ["verified"]})["total"] == 0
    assert viewer.items({"kind": ["journal"], "status": ["__none__"]})["total"] == 1
    assert viewer.items({"from": ["2999-01-01"]})["total"] == 0
    assert not found["errors"] and not found["truncated"]


def test_viewer_has_no_unscoped_metadata_or_http_process_control(viewer):
    with ViewerServer(viewer.catalog.brain, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ["/health", "/api/health", "/api/status"]:
                with pytest.raises(HTTPError) as error:
                    urlopen(server.origin + path, timeout=5)
                assert error.value.code == 404
            request = Request(
                server.url + "api/session/stop",
                data=b"",
                method="POST",
                headers={"Origin": server.origin},
            )
            with pytest.raises(HTTPError) as error:
                urlopen(request, timeout=5)
            assert error.value.code == 405
            with urlopen(server.url + "api/items", timeout=5) as response:
                assert response.status == 200
            assert thread.is_alive()
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_source_choices_keep_empty_unavailable_and_other_configured_roots(viewer, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    viewer.catalog.brain.config["documentation_roots"].update(
        {"empty": str(empty), "missing": str(tmp_path / "missing")}
    )
    before = {p: p.read_bytes() for p in viewer.catalog.brain.state.rglob("*") if p.is_file()}
    for selected in [None, "docs", "empty", "missing"]:
        params = {"kind": ["documentation"]}
        if selected:
            params["source"] = [selected]
        result = viewer.items(params)
        assert result["facets"]["source"] == ["docs", "empty", "missing"]
        if selected == "empty":
            assert result["result_state"] == "empty-catalog"
        if selected == "missing":
            assert result["result_state"] == "unavailable"
    assert viewer.items({"kind": ["note"]})["facets"]["source"] == ["personal"]
    assert viewer.items({})["facets"]["source"] == ["docs", "empty", "missing", "personal"]
    assert not (tmp_path / "missing").exists()
    assert before == {
        p: p.read_bytes() for p in viewer.catalog.brain.state.rglob("*") if p.is_file()
    }


def test_viewer_reports_empty_no_match_partial_failure_and_limit(viewer, tmp_path, monkeypatch):
    assert viewer.items({"q": ["no-such-synthetic-term"]})["result_state"] == "no-matches"
    empty = tmp_path / "empty-docs"
    empty.mkdir()
    viewer.catalog.brain.config["documentation_roots"]["empty"] = str(empty)
    assert viewer.items({"source": ["empty"]})["result_state"] == "empty-catalog"
    (empty / "bad.md").write_bytes(b"\xff")
    failed = viewer.items({"source": ["empty"]})
    assert failed["result_state"] == "unavailable" and failed["total"] == 0
    partial = viewer.items({})
    assert partial["result_state"] == "ready" and partial["total"] > 0
    assert partial["diagnostics"]["status"] == "partial"
    assert viewer.items({"q": ["no-such-synthetic-term"]})["result_state"] == "partial"
    monkeypatch.setattr(viewer.catalog, "MAX_ENTRIES", 0)
    assert viewer.items({})["result_state"] == "limited"


def test_http_persistent_incoherent_content_is_not_an_empty_store(viewer, monkeypatch):
    def refused(*args, **kwargs):
        raise ValueError("Path escapes root: synthetic-private-detail")

    before = {p: p.read_bytes() for p in viewer.catalog.brain.vault.rglob("*") if p.is_file()}
    monkeypatch.setattr(viewer.catalog, "_row", refused)
    with ViewerServer(viewer.catalog.brain, 0) as server:
        server.viewer = viewer
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for _ in range(2):
                with urlopen(server.url + "api/items?kind=note", timeout=5) as response:
                    result = json.loads(response.read())
                assert result["result_state"] == "unavailable"
                assert result["diagnostics"]["registered_notes"] == 1
                assert result["diagnostics"]["readable_notes"] == 0
                assert "ledger-catalog-mismatch" in result["diagnostics"]["codes"]
                assert "synthetic-private-detail" not in json.dumps(result)
                assert str(viewer.catalog.brain.vault) not in json.dumps(result)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert before == {
        p: p.read_bytes() for p in viewer.catalog.brain.vault.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("scenario", ["empty", "no-matches", "unavailable", "partial", "limited"])
def test_http_catalog_states_use_real_synthetic_sources(viewer, tmp_path, monkeypatch, scenario):
    from second_brain.catalog import Catalog

    docs = tmp_path / "state-docs"
    docs.mkdir()
    viewer.catalog.brain.config["documentation_roots"] = {"docs": str(docs)}
    if scenario in {"no-matches", "partial", "limited"}:
        (docs / "ok.md").write_text("# Synthetic readable guide", encoding="utf-8")
    if scenario in {"unavailable", "partial"}:
        (docs / "invalid.md").write_bytes(b"\xff")
    if scenario == "limited":
        monkeypatch.setattr(Catalog, "MAX_ENTRIES", 0)
    query = "api/items?kind=documentation" + ("&q=not-found" if scenario == "no-matches" else "")
    with ViewerServer(viewer.catalog.brain, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(server.url + query, timeout=5) as response:
                result = json.loads(response.read())
        finally:
            server.shutdown()
            thread.join(timeout=5)
    expected = {"empty": "empty-catalog", "partial": "ready"}.get(scenario, scenario)
    assert result["result_state"] == expected
    if scenario == "partial":
        assert result["total"] == 1 and result["diagnostics"]["status"] == "partial"
    if scenario == "limited":
        assert result["truncated"] and "scan-limit" in result["diagnostics"]["codes"]


def test_content_disappearing_after_snapshot_updates_diagnostics(viewer, monkeypatch):
    def changed(*args, **kwargs):
        raise ValueError("Synthetic private path must not escape")

    monkeypatch.setattr(viewer.catalog, "read", changed)
    result = viewer.items({"kind": ["note"]})
    assert result["result_state"] == "unavailable"
    assert result["diagnostics"]["readable_notes"] == 0
    assert "content-changed" in result["diagnostics"]["codes"]
    assert "Synthetic private path" not in json.dumps(result)


@pytest.mark.parametrize(
    "params",
    [
        {"root": ["outside"]},
        {"from": ["bad"]},
        {"from": ["2026-10-17"], "to": ["2026-10-16"]},
        {"sort": ["unknown"]},
        {"offset": ["-1"]},
        {"q": ["a", "b"]},
    ],
)
def test_invalid_viewer_filters_rejected(viewer, params):
    with pytest.raises(ValueError):
        viewer.items(params)


def test_safe_markdown_and_scoped_link_navigation(viewer):
    hostile = viewer.content("documentation:docs:hostile.md")
    assert "<script>" not in hostile["html"] and "<img" not in hostile["html"]
    assert 'href="javascript:' not in hostile["html"]
    index = viewer.content("documentation:docs:index.md")
    assert 'data-content-id="documentation:docs:guide.md"' in index["html"]
    assert 'data-unavailable="true"' in index["html"]
    assert 'rel="noopener noreferrer"' in index["html"]
    guide = viewer.content("documentation:docs:guide.md")
    assert "<table>" in guide["html"] and guide["headings"][0]["title"] == "Instalación"
    journal = viewer.items({"kind": ["journal"]})["items"][0]
    assert "<!-- event:" not in journal["preview"]
    journal_content = viewer.content(journal["id"])
    assert 'data-content-id="note:personal:git"' in journal_content["html"]
    assert "<!-- event:" not in journal_content["html"]
    for content_id in [
        "documentation:docs:../private.md",
        "documentation:docs:credentials.md",
        "note:personal:missing",
    ]:
        with pytest.raises(ValueError):
            viewer.content(content_id)


def test_viewer_paging_and_read_only_files(viewer):
    from pathlib import Path

    brain = viewer.catalog.brain
    docs = Path(brain.config["documentation_roots"]["docs"])
    for i in range(24):
        (docs / f"extra-{i}.md").write_text(f"# Documento {i:02}\n\nEjemplo", encoding="utf-8")
    roots = [docs, brain.vault, brain.state]
    before = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
    first = viewer.items({"kind": ["documentation"], "sort": ["title"]})
    second = viewer.items({"kind": ["documentation"], "sort": ["title"], "offset": ["20"]})
    assert first["total"] == 27 and first["next_offset"] == 20 and len(first["items"]) == 20
    assert len(second["items"]) == 7 and second["next_offset"] is None
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    viewer.content(first["items"][0]["id"])
    assert before == {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}


def test_http_viewer_auth_origin_static_and_read_only_routes(viewer):
    with ViewerServer(viewer.catalog.brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            assert server.server_address[0] == "127.0.0.1"
            with urlopen(server.url, timeout=5) as response:
                assert "Biblioteca" in response.read().decode("utf-8")
                assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
                assert response.headers["Cache-Control"] == "no-store"
                assert response.headers.get("Access-Control-Allow-Origin") is None
            for asset in ["app.js", "style.css"]:
                with urlopen(server.url + asset, timeout=5) as response:
                    assert response.status == 200
            with urlopen(
                server.url + "api/items?" + urlencode({"q": "busquedas"}), timeout=5
            ) as response:
                assert json.loads(response.read())["total"] == 1
            with urlopen(
                server.url + "api/content?" + urlencode({"id": "documentation:docs:guide.md"}),
                timeout=5,
            ) as response:
                assert "<table>" in json.loads(response.read())["html"]
            for headers in [
                {"Host": "attacker.test"},
                {"Origin": "https://attacker.test"},
                {"Sec-Fetch-Site": "cross-site"},
            ]:
                with pytest.raises(HTTPError) as error:
                    urlopen(Request(server.url + "api/items", headers=headers), timeout=5)
                assert error.value.code == 403
            for method in ["POST", "PUT", "DELETE", "PATCH"]:
                with pytest.raises(HTTPError) as error:
                    urlopen(Request(server.url + "api/items", method=method), timeout=5)
                assert error.value.code == 405
            for url in [server.origin + "/api/items", server.url + "../../config.json"]:
                with pytest.raises(HTTPError) as error:
                    urlopen(url, timeout=5)
                assert error.value.code == 404
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("scope", ["personal", "work"])
def test_viewer_info_uses_configured_scope_and_server_day(viewer, scope):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    brain = viewer.catalog.brain
    brain.scope = scope
    brain.now = lambda: datetime(2026, 10, 31, 0, 5, tzinfo=ZoneInfo("Europe/Madrid"))
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(server.url + "api/viewer-info", timeout=5) as response:
                assert json.loads(response.read()) == {"scope": scope, "today": "2026-10-31"}
                assert response.headers["Cache-Control"] == "no-store"
            for url, headers, expected in [
                (server.origin + "/api/viewer-info", {}, 404),
                (server.url + "api/viewer-info?scope=personal", {}, 400),
                (server.url + "api/viewer-info", {"Origin": "https://attacker.test"}, 403),
            ]:
                with pytest.raises(HTTPError) as error:
                    urlopen(Request(url, headers=headers), timeout=5)
                assert error.value.code == expected
        finally:
            server.shutdown()
            thread.join(timeout=5)
