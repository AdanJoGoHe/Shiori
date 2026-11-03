"""Observe bounded HTTP responses and Python heap on disposable small/large profiles."""

import json
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path
from urllib.request import urlopen

from second_brain.agent_log import AgentLog, decode
from second_brain.core import Brain, atomic_write
from second_brain.viewer import Viewer, ViewerServer


def scenario(root, scope, pages, marks, events):
    docs = root / "docs"
    docs.mkdir(parents=True)
    commands = [f"echo synthetic-{i:04}" for i in range(marks)]
    (docs / "commands.md").write_text(
        "# Comandos sintéticos\n\n```sh\n" + "\n".join(commands) + "\n```\n", encoding="utf-8"
    )
    for index in range(pages - 1):
        (docs / f"guide-{index:04}.md").write_text(
            f"# Guía ficticia {index}\n\nContexto de ejemplo para comprobar búsqueda y paginación.\n",
            encoding="utf-8",
        )
    brain = Brain(
        dict(
            scope=scope,
            timezone="Europe/Madrid",
            vault_path=str(root / "vault"),
            state_path=str(root / "state"),
            documentation_roots={"demo": str(docs)},
        )
    )
    viewer = Viewer(brain)
    document = viewer.content("documentation:demo:commands.md")
    for command in commands:
        start = document["text"].index(command)
        viewer.annotations.save(
            document,
            dict(
                document_id=document["item"]["id"],
                revision=document["revision"],
                start=start,
                end=start + len(command),
                quote=command,
                color="green",
                tags=["comando"],
            ),
        )
    log = AgentLog(brain)
    log.configure(True, 0)
    action = dict(
        schema_version=1,
        scope=scope,
        event_id="scale-event",
        agent="manual",
        session="scale-session",
        project="demo",
        occurred_at=None,
        kind="command-proposed",
        outcome="unknown",
        summary="Acción sintética",
        command="echo scale",
        context="Fixture",
        references=[],
        corrects=None,
        correction_reason="",
        coverage="reported",
    )
    log.record(action)
    data = log.export()
    template = data["items"][0]
    data["items"] = [{**template, "event_id": f"scale-{index:05}"} for index in range(events)]
    data["revision"] = events + 1
    raw = json.dumps(data, ensure_ascii=False)
    decode(raw)  # Batch fixture construction still uses the production schema validation.
    atomic_write(brain.state / "agent-log.json", raw)
    result = dict(scope=scope, pages=pages, marks=marks, events=events, measurements=[])
    with ViewerServer(brain) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(path):
            with urlopen(server.url + path, timeout=120) as response:
                payload = response.read()
            return json.loads(payload), len(payload)

        try:
            for name, path, total in [
                ("library", "api/items?view=documents", pages),
                ("fragments", "api/items?view=fragments&category=comando", marks),
                ("agent-log", "api/agent-log", events),
            ]:
                started = time.perf_counter()
                page, size = request(path)
                elapsed = time.perf_counter() - started
                assert page["total"] == total and 0 < len(page["items"]) <= 20
                assert size < 128000
                if name == "agent-log":
                    assert len(json.dumps(page, ensure_ascii=False)) <= 8000
                if page["next_offset"] is not None:
                    separator = "&" if "?" in path else "?"
                    second, _ = request(path + separator + "offset=" + str(page["next_offset"]))
                    key = (
                        "event_id"
                        if name == "agent-log"
                        else "id"
                        if name == "library"
                        else "annotation"
                    )

                    def identity(row):
                        return row[key]["id"] if key == "annotation" else row[key]

                    assert not {identity(row) for row in page["items"]} & {
                        identity(row) for row in second["items"]
                    }
                tracemalloc.start()
                request(path)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                result["measurements"].append(
                    dict(
                        operation=name,
                        seconds=round(elapsed, 4),
                        response_bytes=size,
                        returned=len(page["items"]),
                        python_heap_peak_bytes=peak,
                    )
                )
            if events == 10000:
                before = (brain.state / "agent-log.json").read_bytes()
                try:
                    log.record({**action, "event_id": "over-capacity"})
                except ValueError:
                    pass
                else:
                    raise AssertionError("Log capacity silently exceeded")
                assert (brain.state / "agent-log.json").read_bytes() == before
        finally:
            if tracemalloc.is_tracing():
                tracemalloc.stop()
            server.shutdown()
            thread.join(5)
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="shiori-scale-check-") as temporary:
        root = Path(temporary)
        results = [
            scenario(root / "small", "personal", 12, 5, 20),
            scenario(root / "large", "work", 1000, 500, 10000),
        ]
        print(
            json.dumps(
                dict(
                    status="passed",
                    data="synthetic-only",
                    timing="uninstrumented first request; machine-dependent",
                    memory="Python heap during a separate traced request, not process RSS",
                    results=results,
                )
            )
        )


if __name__ == "__main__":
    main()
