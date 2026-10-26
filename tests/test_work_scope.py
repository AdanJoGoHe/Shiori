"""Only synthetic fixtures: verify application scope isolation, not OS sandboxing."""

import asyncio
import json

import pytest
from fastmcp import Client

from second_brain.annotations import Annotations
from second_brain.backup import backup, restore
from second_brain.catalog import Catalog
from second_brain.context import build_context
from second_brain.core import Brain, load_config
from second_brain.install import deployment_config, uninstall
from second_brain.provider import project_name, validate_config, ProviderUnavailable
from second_brain.quality import classify_capture
from second_brain.server import create_server
from second_brain.store import MARKER
from second_brain.transfer import import_memory
from test_core import event


def config(root, scope="work"):
    return {
        "schema_version": 1,
        "scope": scope,
        "vault_path": str(root / "vault"),
        "state_path": str(root / "state"),
        "timezone": "UTC",
    }


@pytest.mark.parametrize("scope", ["personal", "work"])
def test_scope_roundtrip_and_opposite_scope_denial(tmp_path, scope):
    cfg = config(tmp_path / scope, scope)
    brain = Brain(cfg)
    candidate = event(scope=scope)
    brain.capture(candidate)
    assert brain.status()["scope"] == scope
    assert build_context(brain, "git")["scope"] == scope
    assert Catalog(brain).list("note")["items"][0]["source"] == scope
    opposite = "personal" if scope == "work" else "work"
    with pytest.raises(ValueError):
        brain.capture(event(scope=opposite, event_id="wrong"))
    before = brain.ledger()
    with pytest.raises(ValueError):
        Brain(dict(cfg, scope=opposite))
    assert brain.ledger() == before
    bundle = tmp_path / "bundle"
    backup(brain, bundle)
    restored = tmp_path / "restored"
    restore(bundle, restored)
    recovered = Brain(load_config(restored / "config.json"))
    assert recovered.scope == scope and recovered.status()["paused"]
    assert recovered.read(candidate["id"]) == brain.read(candidate["id"])
    target = Brain(config(tmp_path / "opposite", opposite))
    for apply in [False, True]:
        with pytest.raises(ValueError, match="scope"):
            import_memory(target, bundle, apply)
    assert target.ledger() == {"notes": {}, "events": {}}


@pytest.mark.parametrize("existing", ["vault", "state", "both"])
def test_work_does_not_adopt_existing_even_empty_roots(tmp_path, existing):
    cfg = config(tmp_path)
    for field in ("vault_path", "state_path"):
        if existing == "both" or existing in field:
            __import__("pathlib").Path(cfg[field]).mkdir()
    with pytest.raises(ValueError, match="identity"):
        Brain(cfg)
    assert not list(tmp_path.rglob(MARKER))


def test_work_rejects_mixed_roots_and_changed_markers_before_retrieval(tmp_path):
    first, second = (Brain(config(tmp_path / name)) for name in ["first", "second"])
    first.capture(event(scope="work"))
    with pytest.raises(ValueError, match="identity"):
        Brain(dict(first.config, state_path=str(second.state)))
    (first.state / MARKER).write_bytes((second.state / MARKER).read_bytes())
    for operation in [
        first.status,
        lambda: first.read("git-version"),
        lambda: first.pause(True),
        lambda: Annotations(first).export(),
        lambda: Catalog(first).list("journal"),
    ]:
        with pytest.raises(ValueError, match="identity"):
            operation()
    assert not (first.state / "paused").exists()


def test_work_provider_and_classifier_do_not_fall_back_to_personal(tmp_path):
    cfg = config(tmp_path)
    cfg["basic_memory_config_dir"] = str(tmp_path / "state/basic-memory")
    brain = Brain(cfg)
    provider_dir = brain.state / "basic-memory"
    provider_dir.mkdir()
    settings = provider_dir / "config.json"
    settings.write_text(
        json.dumps(
            {"projects": {"second-brain-personal": {"path": str(brain.vault), "mode": "local"}}}
        )
    )
    with pytest.raises(ProviderUnavailable):
        validate_config(cfg)
    assert project_name(cfg) == "second-brain-work"
    settings.write_text(
        json.dumps({"projects": {"second-brain-work": {"path": str(brain.vault), "mode": "local"}}})
    )
    validate_config(cfg)
    for material in ["personal", "customer", "unknown", "corporate"]:
        result = classify_capture(
            brain,
            event(scope="work"),
            {
                "material": material,
                "reusable": True,
                "meaningful": True,
                "evidence_kind": "observed",
            },
        )
        assert result["decision"] == ("save" if material == "corporate" else "deny")


def test_annotation_exports_cannot_cross_scopes(tmp_path):
    personal = Annotations(Brain(config(tmp_path / "personal", "personal")))
    work = Annotations(Brain(config(tmp_path / "work")))
    assert work.export()["scope"] == "work"
    for target, source in [(personal, work), (work, personal)]:
        with pytest.raises(ValueError, match="scope"):
            target.restore(json.dumps(source.export()))
        assert not (target.brain.state / "annotations.json").exists()
    work.restore(json.dumps(work.export()))
    backup(work.brain, tmp_path / "bundle")
    restore(tmp_path / "bundle", tmp_path / "restored")
    assert (
        Annotations(Brain(load_config(tmp_path / "restored/config.json"))).export() == work.export()
    )


def test_personal_host_installer_refuses_work_config(tmp_path):
    cfg = config(tmp_path)
    Brain(cfg)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    for operation in [deployment_config, uninstall]:
        with pytest.raises(ValueError, match="personal scope only"):
            operation(path)


def test_work_mcp_tools_require_work_scope(tmp_path):
    async def scenario():
        async with Client(create_server(config(tmp_path))) as client:
            tools = await client.list_tools()
            assert len(tools) == 8
            result = await client.call_tool("memory_status", {})
            assert result.data["scope"] == "work"
            result = await client.call_tool("capture_memory", {"candidate": event()})
            assert result.data["status"] == "failed"
            result = await client.call_tool(
                "capture_memory",
                {"candidate": event(scope="work", source_agent="augment-jetbrains")},
            )
            assert result.data["status"] == "saved"
            result = await client.call_tool("get_context", {"query": "git"})
            assert result.data["scope"] == "work" and len(result.data["notes"]) == 1

    asyncio.run(scenario())
