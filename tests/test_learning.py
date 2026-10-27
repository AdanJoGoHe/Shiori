import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from second_brain.core import Brain
from second_brain.learning import Learning
from test_core import event


@pytest.fixture(params=["personal", "work"])
def learner(tmp_path, request):
    brain = Brain(
        {
            "schema_version": 1,
            "scope": request.param,
            "vault_path": str(tmp_path / "vault"),
            "state_path": str(tmp_path / "state"),
            "timezone": "UTC",
        }
    )
    brain.capture(event(scope=brain.scope, project="synthetic"))
    return Learning(brain)


def proposal(learner, **changes):
    return {
        "scope": learner.brain.scope,
        "id": "git-check",
        "source_id": "git-version",
        "project": "synthetic",
        "description": "Check Git before a synthetic workflow",
        "instructions": "1. Check that Git is installed.\n2. Run git --version.\n3. Inspect the result.",
        "change": "correction",
        "capabilities": ["read", "run-commands"],
        **changes,
    }


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def activate(learner, tmp_path, host="codex"):
    learner.propose(proposal(learner), apply=True)
    directory = tmp_path / host / "skills"
    result = learner.export("git-check", host, directory, apply=True)
    return directory, Path(result["paths"][0])


def test_preview_is_read_only_then_proposal_is_private_and_idempotent(learner, tmp_path):
    before = snapshot(tmp_path)
    result = learner.propose(proposal(learner))
    assert result["status"] == "proposed" and result["applied"] is False
    assert snapshot(tmp_path) == before and not learner.root.exists()
    saved = learner.propose(proposal(learner), apply=True)
    assert saved["applied"] and not learner.read("git-check")["exports"]
    assert learner.propose(proposal(learner), apply=True)["status"] == "unchanged"
    assert learner.propose(proposal(learner, id="duplicate"), apply=True)["id"] == "git-check"
    assert len(learner.rows()) == 1
    with pytest.raises(ValueError, match="explicit activation"):
        learner.export("git-check", refresh=True, apply=True)


@pytest.mark.parametrize("host", ["codex", "augment"])
def test_review_activation_then_owned_correction_and_stale_guards(learner, tmp_path, host):
    directory, target = activate(learner, tmp_path, host)
    original = target.read_bytes()
    metadata = yaml.safe_load(original.decode().split("---", 2)[1])
    assert metadata["name"] == f"shiori-{learner.brain.scope}-git-check"
    assert learner.deployment in original.decode()
    learner.brain.capture(
        event(
            scope=learner.brain.scope,
            project="synthetic",
            event_id="correction",
            body="Run git --version and inspect its output.",
        )
    )
    assert learner.check("git-check")["status"] == "stale"
    with pytest.raises(ValueError, match="canonical proposal"):
        learner.export("git-check", refresh=True, apply=True)
    learner.propose(
        proposal(learner, instructions="1. Run git --version.\n2. Check the observed version."),
        apply=True,
    )
    assert learner.check("git-check", revision=1)["status"] == "stale"
    before = target.read_bytes()
    assert learner.export("git-check", refresh=True)["applied"] is False
    assert target.read_bytes() == before
    assert learner.export("git-check", refresh=True, apply=True)["status"] == "refreshed"
    assert target.read_bytes() != original
    assert learner.check("git-check", learner.deployment, 2)["status"] == "ready"
    assert original in [path.read_bytes() for path in (learner.root / "history").glob("*.md")]


@pytest.mark.parametrize("change", ["capabilities", "project", "source", "declared-expansion"])
def test_expanded_workflow_requires_fresh_activation(learner, tmp_path, change):
    directory, target = activate(learner, tmp_path)
    original = target.read_bytes()
    changes = {"instructions": "1. Inspect the new synthetic procedure."}
    if change == "capabilities":
        changes["capabilities"] = ["read", "run-commands", "network"]
    elif change in {"project", "source"}:
        new_id = "another-source"
        project = "other" if change == "project" else "synthetic"
        learner.brain.capture(
            event(scope=learner.brain.scope, project=project, id=new_id, event_id="other")
        )
        changes.update(source_id=new_id, project=project)
    else:
        changes["change"] = "expansion"
    learner.propose(proposal(learner, **changes), apply=True)
    with pytest.raises(ValueError, match="activation"):
        learner.export("git-check", refresh=True, apply=True)
    assert target.read_bytes() == original
    assert learner.export("git-check", "codex", directory, apply=True)["applied"]


def test_foreign_or_edited_skills_never_overwritten_even_on_create(learner, tmp_path):
    learner.propose(proposal(learner), apply=True)
    directory = tmp_path / "host/skills"
    target = learner.target(learner.read("git-check"), "codex", directory)
    target.parent.mkdir(parents=True)
    target.write_text("a human skill", encoding="utf-8")
    with pytest.raises(ValueError, match="Foreign or edited"):
        learner.export("git-check", "codex", directory, apply=True)
    assert target.read_text() == "a human skill"
    clean, owned = activate(learner, tmp_path, "augment")
    owned.write_text("human correction", encoding="utf-8")
    for action in [
        lambda: learner.export("git-check", "augment", clean, apply=True),
        lambda: learner.export("git-check", refresh=True, apply=True),
        lambda: learner.archive("git-check", apply=True),
    ]:
        with pytest.raises(ValueError):
            action()
    assert owned.read_text() == "human correction"


def test_archive_only_owned_files_preserves_memory_and_history(learner, tmp_path):
    _, target = activate(learner, tmp_path)
    original, note = target.read_bytes(), learner.brain.read("git-version")
    assert learner.archive("git-check")["applied"] is False and target.exists()
    assert learner.archive("git-check", apply=True)["applied"] and not target.exists()
    assert learner.check("git-check")["status"] == "archived"
    assert learner.brain.read("git-version") == note
    assert original in [path.read_bytes() for path in (learner.root / "history").glob("*.md")]
    assert learner.propose(proposal(learner), apply=True)["revision"] == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "other"},
        {"id": "../escape"},
        {"id": "two--hyphens"},
        {"id": "x" * 41},
        {"source_id": "missing"},
        {"project": "other"},
        {"instructions": "password=synthetic123"},
        {"instructions": "\n".join("line" for _ in range(26))},
        {"capabilities": ["anything"]},
        {"transcript_path": "unapproved"},
        {"change": "unknown"},
    ],
)
def test_invalid_proposals_do_not_create_learning_state(learner, changes):
    with pytest.raises(ValueError):
        learner.propose(proposal(learner, **changes), apply=True)
    assert not learner.root.exists()


def test_unverified_source_pause_and_wrong_deployment_block_learning(learner, tmp_path):
    learner.brain.capture(
        event(
            scope=learner.brain.scope,
            project="synthetic",
            event_id="unverified",
            status="unverified",
        )
    )
    with pytest.raises(ValueError, match="verified note"):
        learner.propose(proposal(learner), apply=True)
    learner.brain.capture(
        event(scope=learner.brain.scope, project="synthetic", event_id="verified")
    )
    activate(learner, tmp_path)
    with pytest.raises(ValueError, match="another deployment"):
        learner.check("git-check", "wrong-deployment")
    learner.brain.pause(True)
    for action in [
        lambda: learner.propose(proposal(learner), apply=True),
        lambda: learner.export("git-check", refresh=True, apply=True),
    ]:
        with pytest.raises(ValueError, match="paused"):
            action()


def test_export_refuses_git_and_memory_roots(learner, tmp_path):
    learner.propose(proposal(learner), apply=True)
    project = tmp_path / "public-project"
    (project / ".git").mkdir(parents=True)
    for directory in [
        project / ".agents/skills",
        learner.brain.vault / "skills",
        learner.brain.state / "skills",
    ]:
        with pytest.raises(ValueError):
            learner.export("git-check", "codex", directory, apply=True)


def test_partial_activation_cannot_adopt_an_unrecorded_host_file(learner, tmp_path, monkeypatch):
    import second_brain.learning as module

    learner.propose(proposal(learner), apply=True)
    directory = tmp_path / "host/skills"
    target = learner.target(learner.read("git-check"), "codex", directory)
    write = module.atomic_write

    def fail_record_after_host_write(path, content):
        if path == learner.path("git-check") and target.exists():
            raise OSError("Synthetic interrupted activation")
        write(path, content)

    monkeypatch.setattr(module, "atomic_write", fail_record_after_host_write)
    with pytest.raises(OSError, match="interrupted"):
        learner.export("git-check", "codex", directory, apply=True)
    original = target.read_bytes()
    assert learner.read("git-check")["exports"] == []
    with pytest.raises(ValueError, match="Foreign or edited"):
        learner.export("git-check", "codex", directory, apply=True)
    assert target.read_bytes() == original
    assert learner.brain.read("git-version")


def test_activation_destination_limit_does_not_create_extra_files(learner, tmp_path):
    learner.propose(proposal(learner), apply=True)
    for number in range(4):
        learner.export("git-check", "codex", tmp_path / f"host-{number}/skills", apply=True)
    with pytest.raises(ValueError, match="four approved"):
        learner.export("git-check", "codex", tmp_path / "extra/skills", apply=True)
    assert not (tmp_path / "extra").exists()


def test_cli_guide_and_learning_lifecycle(learner, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(learner.brain.config), encoding="utf-8")
    request = tmp_path / "request.json"
    request.write_text(json.dumps(proposal(learner)), encoding="utf-8")

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "second_brain.cli", "--config", str(config), "learn", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    assert cli("guide")["scope"] == learner.brain.scope
    assert cli("propose", "--request-file", str(request), "--apply")["applied"]
    assert len(cli("list")["items"]) == 1
    assert cli(
        "activate",
        "--id",
        "git-check",
        "--host",
        "augment",
        "--skills-dir",
        str(tmp_path / "host/skills"),
        "--apply",
    )["applied"]
    assert (
        cli(
            "check",
            "--id",
            "git-check",
            "--expect-deployment",
            learner.deployment,
            "--expect-revision",
            "1",
        )["status"]
        == "ready"
    )
