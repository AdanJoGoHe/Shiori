from pathlib import Path

import pytest

from second_brain.annotations import resolve_anchor
from test_annotations import selection
from test_viewer import viewer as viewer


def anchor(text, quote, start=None):
    start = text.index(quote) if start is None else start
    end = start + len(quote)
    return {
        "quote": quote,
        "start": start,
        "end": end,
        "prefix": text[max(0, start - 120) : start],
        "suffix": text[end : end + 120],
        "revision": "old",
    }


def test_exact_revision_keeps_original_duplicate_and_unicode_offsets():
    text = "😀 echo\necho"
    item = anchor(text, "echo", 7)
    result = resolve_anchor(item, {"revision": "old", "text": text})
    assert result == {
        "status": "resolved",
        "reason": "current",
        "start": 7,
        "end": 11,
        "revision": "old",
    }


def test_shifted_quote_uses_context_not_nearest_offset():
    text = "A" * 150 + "echo 😀" + "Z" * 150
    item = anchor(text, "echo 😀")
    changed = "Inserted paragraph\n" + text
    result = resolve_anchor(item, {"revision": "new", "text": changed})
    assert result["reason"] == "reattached"
    assert changed[result["start"] : result["end"]] == "echo 😀"
    assert result["start"] != item["start"]


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ("left quote right", "reattached"),
        ("left removed right", "missing"),
        ("other quote context", "context-changed"),
        ("left quote right | left quote right", "ambiguous"),
        ("other quote context | another quote context", "ambiguous"),
    ],
)
def test_changed_revision_requires_unique_exact_context(changed, reason):
    item = anchor("left quote right", "quote")
    original = dict(item)
    result = resolve_anchor(item, {"revision": "new", "text": changed})
    assert result["reason"] == reason
    assert (result["start"] is None) == (result["status"] == "unresolved")
    assert item == original


def test_duplicate_with_distinct_context_resolves_but_offsets_cannot_break_ties():
    original = "A" * 150 + "quote" + "Z" * 150
    item = anchor(original, "quote")
    assert resolve_anchor(item, {"revision": "new", "text": original * 2})["reason"] == "ambiguous"
    changed = "unrelated quote elsewhere\n" + original
    assert resolve_anchor(item, {"revision": "new", "text": changed})["start"] == changed.rindex(
        "quote"
    )


def test_empty_context_is_boundary_not_wildcard_and_matches_overlap():
    item = anchor("abc", "abc")
    assert resolve_anchor(item, {"revision": "new", "text": "abc"})["reason"] == "reattached"
    assert resolve_anchor(item, {"revision": "new", "text": "prefix abc"})["status"] == "unresolved"
    assert (
        resolve_anchor(anchor("aaa", "aa"), {"revision": "new", "text": "aaaa"})["status"]
        == "unresolved"
    )


def test_reader_recheck_relink_missing_source_and_delete_preserve_store(viewer):
    payload = selection(viewer)
    saved = viewer.save_annotation(payload)
    path = Path(viewer.catalog.brain.config["documentation_roots"]["docs"]) / "guide.md"
    source = path.read_text(encoding="utf-8")
    store = viewer.catalog.brain.state / "annotations.json"
    before = store.read_bytes()
    path.write_text(source.replace("Búsquedas locales", "**Búsquedas locales**"), encoding="utf-8")
    row = viewer.annotation_items(saved["document_id"])["items"][0]
    assert row["anchor"]["reason"] == "reattached"
    assert store.read_bytes() == before
    path.write_text("# Replacement\n\nNew selection 😀\n", encoding="utf-8")
    assert (
        viewer.annotation_items(saved["document_id"])["items"][0]["anchor"]["reason"] == "missing"
    )
    doc = viewer.content(saved["document_id"])
    quote = "New selection 😀"
    start = doc["text"].index(quote)
    updated = viewer.save_annotation(
        {
            **payload,
            "revision": doc["revision"],
            "start": start,
            "end": start + len(quote),
            "quote": quote,
            "version": 1,
        },
        saved["id"],
    )
    assert updated["id"] == saved["id"] and updated["version"] == 2
    assert updated["tags"] == saved["tags"] and updated["color"] == saved["color"]
    path.unlink()
    unavailable = viewer.annotation_items(saved["document_id"])["items"][0]
    assert unavailable["quote"] == quote
    assert unavailable["anchor"]["reason"] == "unavailable"
    assert unavailable["anchor"]["start"] is None
    viewer.annotations.delete(saved["id"], 2)
    with pytest.raises(ValueError):
        viewer.annotation_items(saved["document_id"])
    with pytest.raises(ValueError):
        viewer.annotation_items("documentation:docs:../private.md")
