"""Exercise complete recovery on owned disposable fixtures, never an existing profile."""

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from second_brain.agent_log import AgentLog
from second_brain.backup import backup, restore, read_bundle
from second_brain.core import Brain, load_config
from second_brain.favorites import Favorites
from second_brain.task_pages import TaskPages
from second_brain.viewer import Viewer
from second_brain.workflow import overview


def verify_recovery(brain, folder):
    base = folder.parent.resolve()
    assert base.parent == Path(tempfile.gettempdir()).resolve()
    assert base.name.startswith(("shiori-release-pair-", "shiori-recovery-check-"))
    assert brain.vault.is_relative_to(base) and brain.state.is_relative_to(base)
    folder.mkdir()
    scope = brain.scope
    assert not Favorites(brain).export()["items"] and not AgentLog(brain).export()["items"]
    assert not AgentLog(brain).status()["enabled"]
    note = dict(
        scope=scope,
        id="recovery-note",
        event_id="recovery-note",
        title="Guía ficticia de recuperación",
        type="knowledge",
        status="verified",
        source_agent="manual",
        project="release-check",
        tags=["demo"],
        body='Comando sintético: `echo "listo 😀"`.',
        evidence="Fixture construido para comprobar recuperación.",
    )
    assert brain.capture(note)["status"] == "saved"
    for version, state in [(0, "open"), (1, "done")]:
        assert (
            brain.capture(
                dict(
                    scope=scope,
                    mode="journal-only",
                    event_id="recovery-task-" + state,
                    source_agent="manual",
                    project="release-check",
                    title="Seguimiento ficticio",
                    summary="Cambio de estado para comprobar historial.",
                    tasks=[
                        dict(
                            id="recovery-follow-up",
                            title="Revisar recuperación",
                            details="Datos ficticios",
                            status=state,
                            version=version,
                        )
                    ],
                )
            )["status"]
            == "saved"
        )
    pages = TaskPages(brain)
    page = pages.save(
        dict(
            key="DEMO-1234",
            title="Recuperación ficticia",
            body="```sh\necho demo\n```",
            status="in-progress",
            project="release-check",
            tags=["demo"],
            links=[
                dict(
                    target=f"note:{scope}:recovery-note",
                    label="Nota del ejemplo",
                    annotation_id=None,
                )
            ],
            version=0,
        )
    )
    viewer = Viewer(brain)
    content = viewer.content(f"note:{scope}:recovery-note")
    quote = 'echo "listo 😀"'
    start = content["text"].index(quote)
    mark = viewer.annotations.save(
        content,
        dict(
            document_id=content["item"]["id"],
            revision=content["revision"],
            start=start,
            end=start + len(quote),
            quote=quote,
            color="green",
            tags=["comando"],
        ),
    )
    favorites = Favorites(brain)
    favorite = favorites.save(
        dict(
            target=content["item"]["id"],
            title="Mi comando ficticio",
            project="release-check",
            tags=["comando"],
            version=0,
        )
    )
    removed = favorites.save(
        dict(
            target="https://example.test/removed",
            title="Referencia quitada",
            project=None,
            tags=[],
            version=0,
        )
    )
    favorites.remove(removed["id"], removed["version"])
    at = datetime.fromisoformat(brain.ledger()["events"]["recovery-task-done"]["at"])
    favorites.save(
        dict(
            target=f"journal:{scope}:{at:%Y}/{at:%Y-%m-%d}.md",
            title="Día del ejemplo",
            project="release-check",
            tags=[],
            version=0,
        )
    )
    log = AgentLog(brain)
    log.configure(True, 0)
    event = dict(
        schema_version=1,
        scope=scope,
        event_id="recovery-action",
        agent="manual",
        session="recovery-session",
        project="release-check",
        occurred_at=None,
        kind="command-executed",
        outcome="success",
        summary="Acción ficticia",
        command=quote,
        context="Solo prueba sintética",
        references=[
            dict(kind="content", target=content["item"]["id"], label="Nota"),
            dict(kind="journal-event", target="recovery-task-done", label="Avance"),
        ],
        corrects=None,
        correction_reason="",
        coverage="reported",
    )
    assert log.record(event)["status"] == "saved"
    assert (
        log.record(
            {
                **event,
                "event_id": "recovery-correction",
                "corrects": event["event_id"],
                "outcome": "unknown",
                "correction_reason": "Corrección sintética",
            }
        )["status"]
        == "saved"
    )
    log.configure(False, log.status()["revision"])
    result = backup(brain, folder / "bundle")
    manifest, files, _ = read_bundle(folder / "bundle", scope)
    assert {
        "state/ledger.json",
        "state/annotations.json",
        "state/task-pages.json",
        "state/agent-log.json",
        "state/favorites.json",
    } <= files.keys()
    assert restore(folder / "bundle", folder / "restored")["paused"]
    restored = Brain(load_config(folder / "restored/config.json"))
    assert restored.scope == scope and restored.status()["paused"]
    assert all((folder / "restored" / name).read_bytes() == raw for name, raw in files.items())
    assert restored.read("recovery-note") == brain.read("recovery-note")
    assert Viewer(restored).annotations.export() == viewer.annotations.export()
    assert any(row["id"] == mark["id"] for row in Viewer(restored).annotations.export()["items"])
    assert TaskPages(restored).read("DEMO-1234") == page
    assert Favorites(restored).export() == favorites.export()
    assert Favorites(restored).query(identity=favorite["id"])["items"][0]["available"]
    assert AgentLog(restored).export() == log.export()
    assert AgentLog(restored).read(event["event_id"])["corrected_by"] == "recovery-correction"
    assert overview(restored, "release-check")["tasks"] == overview(brain, "release-check")["tasks"]
    assert restored.ledger() == brain.ledger()
    assert restored.capture({**note, "event_id": "new-paused-capture"}) == {
        "status": "skipped",
        "reason": "paused",
    }
    restored.pause(False)
    assert restored.capture(note)["status"] == "duplicate"
    for mode in ["hash", "scope"]:
        damaged = folder / ("bad-" + mode)
        shutil.copytree(folder / "bundle", damaged)
        if mode == "hash":
            (damaged / "state/favorites.json").write_text("{}", encoding="utf-8")
        else:
            wrong = {**manifest, "scope": "personal" if scope == "work" else "work"}
            (damaged / "manifest.json").write_text(json.dumps(wrong), encoding="utf-8")
        try:
            restore(damaged, folder / ("denied-" + mode))
        except ValueError:
            pass
        else:
            raise AssertionError("Damaged recovery bundle accepted")
        assert not (folder / ("denied-" + mode)).exists()
    assert all(
        hashlib.sha256((folder / "bundle" / name).read_bytes()).hexdigest() == digest
        for name, digest in manifest["files"].items()
    )
    return dict(
        scope=scope,
        files=result["files"],
        checks=[
            "notes-marks-task-pages-journal-task-history-favorites-removal-log-correction",
            "exact-bytes",
            "paused-restore",
            "deduplicated-retry",
            "hash-and-scope-failure-before-write",
        ],
    )


def main():
    with tempfile.TemporaryDirectory(prefix="shiori-recovery-check-") as temporary:
        root = Path(temporary)
        results = []
        for scope in ["personal", "work"]:
            brain = Brain(
                dict(
                    scope=scope,
                    timezone="Europe/Madrid",
                    vault_path=str(root / scope / "vault"),
                    state_path=str(root / scope / "state"),
                )
            )
            results.append(verify_recovery(brain, root / (scope + "-recovery")))
        print(json.dumps(dict(status="passed", data="synthetic-only", profiles=results)))


if __name__ == "__main__":
    main()
