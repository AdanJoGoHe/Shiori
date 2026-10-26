from pathlib import Path

import pytest

from second_brain.annotations import Conflict
from test_annotations import selection
from test_viewer import viewer as viewer


def test_undo_restores_id_archived_tags_and_orphan_with_new_version(viewer):
    item = viewer.save_annotation(selection(viewer))
    category = next(
        row for row in viewer.annotations.categories()["items"] if row["id"] == item["tags"][0]
    )
    viewer.annotations.save_category(
        {
            key: True if key == "archived" else category[key]
            for key in ("label", "color", "archived", "version")
        },
        category["id"],
    )
    ticket = viewer.delete_annotation(item["id"], 1)
    (Path(viewer.catalog.brain.config["documentation_roots"]["docs"]) / "guide.md").unlink()
    with pytest.raises(Conflict):
        viewer.undo_annotation({"token": "0" * 32})
    restored = viewer.undo_annotation({"token": ticket["undo_token"]})
    assert restored["id"] == item["id"] and restored["version"] == 2
    assert restored["tags"] == item["tags"] and restored["created_at"] == item["created_at"]
    assert (
        viewer.annotation_items(item["document_id"])["items"][0]["anchor"]["reason"]
        == "unavailable"
    )
    with pytest.raises(Conflict):
        viewer.undo_annotation({"token": ticket["undo_token"]})
    with pytest.raises(Conflict):
        viewer.annotations.delete(restored["id"], 1)


def test_latest_delete_replaces_ticket_and_failed_undo_preserves_data(viewer, monkeypatch):
    first = viewer.save_annotation(selection(viewer))
    second = viewer.save_annotation(selection(viewer))
    one = viewer.delete_annotation(first["id"], 1)
    two = viewer.delete_annotation(second["id"], 1)
    with pytest.raises(Conflict):
        viewer.undo_annotation({"token": one["undo_token"]})
    import second_brain.annotations as module

    monkeypatch.setattr(module, "MAX_ITEMS", 0)
    before = viewer.annotations.export()
    with pytest.raises(ValueError):
        viewer.undo_annotation({"token": two["undo_token"]})
    assert viewer.annotations.export() == before
    monkeypatch.setattr(module, "MAX_ITEMS", 1000)
    assert viewer.undo_annotation({"token": two["undo_token"]})["id"] == second["id"]
