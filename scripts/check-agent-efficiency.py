"""Compare scripted agent workflows over real local MCP, CLI and viewer entry points."""

import argparse
import asyncio
import http.client
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter
from urllib.parse import urlsplit

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from second_brain.core import Brain
from second_brain.journal import load_entries
from second_brain.task_pages import FIELDS, TaskPages

PROJECT = "synthetic"
KEY = "DEMO-123"
COMMAND = "kubectl get pods -n demo"
NEXT_STEP = "Review the synthetic rollout"
TASK_BODY = "This authored task body must survive edits."
ENV = {
    "PYTHONUTF8": "1",
    "DO_NOT_TRACK": "1",
    "FASTMCP_SHOW_SERVER_BANNER": "false",
    "FASTMCP_CHECK_FOR_UPDATES": "off",
    "FASTMCP_TELEMETRY_MODE": "off",
}


def note(identity, body, kind="command"):
    return {
        "scope": "work",
        "id": identity,
        "event_id": identity,
        "title": "Synthetic " + identity,
        "type": kind,
        "status": "verified",
        "project": PROJECT,
        "source_agent": "manual",
        "body": body,
        "evidence": "Observed on a disposable fixture.",
    }


def progress(event_id, summary):
    return dict(
        scope="work",
        mode="journal-only",
        event_id=event_id,
        title=f"Progress {KEY}",
        project=PROJECT,
        activity=KEY.lower(),
        source_agent="manual",
        summary=summary,
    )


def link(identity):
    return dict(target=f"note:work:{identity}", label="Synthetic " + identity, annotation_id=None)


def seed(root, now):
    config = dict(
        schema_version=1,
        scope="work",
        timezone="UTC",
        vault_path=str(root / "vault"),
        state_path=str(root / "state"),
    )
    brain = Brain(config)
    brain.now = lambda: now
    for candidate in [
        note("a-decoy", "Synthetic pods demo uses kubectl get events -n other."),
        note(
            "z-command",
            "Kubectl is used to inspect the fixture. "
            + "Synthetic setup context. " * 30
            + f"Run `{COMMAND}` in the example namespace.",
        ),
        note("issue-reference", "Check the synthetic rollout for DEMO-123.", "knowledge"),
    ]:
        assert brain.capture(candidate)["status"] == "saved"
    TaskPages(brain).save(
        dict(
            key=KEY,
            version=0,
            title="Synthetic rollout",
            body=TASK_BODY,
            status="open",
            project=PROJECT,
            tags=["rollout"],
            links=[link("issue-reference")],
        )
    )
    entry = dict(
        progress("resume-fixture", "Checked the fixture"), progress={"next_steps": [NEXT_STEP]}
    )
    assert brain.capture(entry)["status"] == "saved"
    path = root / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return brain, path


@asynccontextmanager
async def viewer(command):
    process = await asyncio.create_subprocess_exec(
        *command,
        "viewer",
        "--port",
        "0",
        env={**os.environ, **ENV},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        origin = urlsplit((await asyncio.wait_for(process.stdout.readline(), 30)).decode().strip())
        if origin.scheme != "http" or origin.hostname != "127.0.0.1" or not origin.port:
            raise ValueError("Expected a disposable loopback viewer")
        yield origin
    finally:
        if process.returncode is None:
            process.terminate()
        await asyncio.wait_for(process.wait(), 10)


class Flow:
    def __init__(self, client, command, origin, current):
        self.client, self.command, self.origin, self.current = client, command, origin, current
        self.counts = dict(
            calls=0,
            response_chars=0,
            response_bytes=0,
            repeated_reads=0,
            capture_errors=0,
            transport_errors=0,
        )
        self.reads = set()

    def response(self, data):
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        self.counts["response_chars"] += len(payload)
        self.counts["response_bytes"] += len(payload.encode("utf-8"))
        return data

    def observe(self, kind, identity):
        key = (kind, identity)
        self.counts["repeated_reads"] += key in self.reads
        self.reads.add(key)

    async def mcp(self, tool, *, hidden=False, **arguments):
        self.counts["calls"] += 1
        try:
            result = await self.client.call_tool(tool, arguments)
        except Exception:
            if tool in {"capture_memory", "record_checkpoint"}:
                self.counts["capture_errors"] += 1
            raise
        return result.data if hidden else self.response(result.data)

    async def cli_capture(self, candidate):
        self.counts["calls"] += 1
        process = await asyncio.create_subprocess_exec(
            *self.command,
            "capture",
            "--event-file",
            "-",
            env={**os.environ, **ENV},
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            raw, _ = await asyncio.wait_for(process.communicate(json.dumps(candidate).encode()), 30)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode:
            self.counts["capture_errors"] += 1
            raise RuntimeError("CLI capture failed")
        return self.response(json.loads(raw))

    def capture_status(self, result, expected):
        if result.get("status") != expected:
            self.counts["capture_errors"] += 1
            raise ValueError("Unexpected capture result")

    def task_http(self, payload=None):
        self.counts["calls"] += 1
        origin = self.origin
        connection = http.client.HTTPConnection(origin.hostname, origin.port, timeout=30)
        try:
            connection.request(
                "GET" if payload is None else "POST",
                origin.path + ("api/tasks?key=" + KEY if payload is None else "api/tasks"),
                body=json.dumps(payload).encode() if payload is not None else None,
                headers={"Origin": f"http://{origin.netloc}", "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status not in (200, 201):
                raise RuntimeError("Viewer task request failed")
            return self.response(json.load(response))
        finally:
            connection.close()

    async def task(self):
        self.observe("task", KEY)
        if self.current:
            return await self.mcp("get_task_page", issue_key=KEY)
        return self.task_http()["item"]

    async def edit(self, page, changes, event_id):
        if self.current:
            result = await self.mcp(
                "save_task_page",
                issue_key=KEY,
                expected_version=page["version"],
                changes=changes,
                event_id=event_id,
            )
            assert result["status"] == "saved"
        else:
            payload = {key: page[key] for key in FIELDS | {"version"}}
            result = self.task_http(dict(payload, **changes))
        assert result["version"] == page["version"] + 1


async def resume(flow):
    if flow.current:
        pack = await flow.mcp("get_work_context", issue_key=KEY)
        assert pack["found"] and not pack["truncated"]
        task, notes, entries = pack["task"], pack["notes"], pack["recent_progress"]
        assert notes[0]["id"] == "issue-reference" and "synthetic rollout" in notes[0]["excerpt"]
        assert entries[0]["suggested_next_step"] == NEXT_STEP
    else:
        task = await flow.task()
        note_id = task["links"][0]["target"].split(":")[-1]
        text = await flow.mcp("read_memory", note_id=note_id)
        flow.observe("note", note_id)
        assert note_id == "issue-reference" and "synthetic rollout" in text
        journal = await flow.mcp("read_journal", project=PROJECT, query=KEY)
        entry = journal["items"][0]
        flow.observe("journal", entry["event_id"])
        assert entry["event_id"] == "resume-fixture" and NEXT_STEP in entry["content"]
    assert task["status"] == "open" and task["version"] == 1


async def find_command(flow):
    result = await flow.mcp("get_context", query=COMMAND, filters={"project": PROJECT})
    for row in result["notes"]:
        flow.observe("note", row["id"])
    if flow.current:
        match = result["notes"][0]
        assert match["id"] == "z-command" and COMMAND in match["excerpt"]
        return
    for row in result["notes"]:
        note_id = row["id"]
        text = row["excerpt"]
        if COMMAND not in text and row["excerpt_truncated"]:
            text = await flow.mcp("read_memory", note_id=note_id)
            flow.observe("note", note_id)
        if COMMAND in text:
            assert note_id == "z-command"
            return
    raise ValueError("Exact command was not recovered")


async def decision(flow):
    candidate = note("bench-decision", "Keep the synthetic rollout gate.", "decision")
    summary = "Recorded the synthetic rollout decision"
    page = await flow.task()
    if flow.current:
        knowledge = {
            key: candidate[key] for key in ("id", "title", "type", "status", "body", "evidence")
        }
        checkpoint = dict(
            scope="work",
            issue_key=KEY,
            expected_version=page["version"],
            event_id=candidate["event_id"],
            source_agent="manual",
            summary=summary,
            knowledge=knowledge,
        )
        saved = await flow.mcp("record_checkpoint", candidate=checkpoint)
        flow.capture_status(saved, "saved")
        assert saved["note_id"] == candidate["id"]
    else:
        candidate.update(summary=summary, activity=KEY.lower())
        classified = await flow.mcp(
            "classify_memory",
            candidate=candidate,
            assessment=dict(
                material="corporate", reusable=True, meaningful=True, evidence_kind="observed"
            ),
        )
        if classified.get("decision") != "save":
            flow.counts["capture_errors"] += 1
            raise ValueError("Expected a reviewed new decision")
        saved = await flow.mcp("capture_memory", candidate=classified["candidate"])
        flow.capture_status(saved, "saved")
        await flow.edit(page, {"links": [*page["links"], link(candidate["id"])]}, "link-decision")


async def edit(flow):
    page = await flow.task()
    await flow.edit(page, {"status": "blocked"}, "edit-fixture")


async def recover(flow):
    candidate = progress("recover-fixture", "Verified the synthetic recovery")
    # Verify the server committed, then simulate the agent losing the write receipt.
    flow.capture_status(await flow.mcp("capture_memory", candidate=candidate, hidden=True), "saved")
    await flow.client.close()
    try:
        await flow.mcp("memory_status")
    except RuntimeError:
        if flow.client.is_connected():
            raise
        flow.counts["transport_errors"] += 1
    else:
        raise RuntimeError("Expected a disconnected MCP client")
    flow.capture_status(await flow.cli_capture(candidate), "duplicate")


def verify_writes(brain, now, scenario):
    if scenario == "decision":
        page = TaskPages(brain).read(KEY)
        assert link("bench-decision") in page["links"]
        assert "Keep the synthetic rollout gate." in brain.read("bench-decision")
    elif scenario == "edit":
        page = TaskPages(brain).read(KEY)
        assert page["status"] == "blocked" and page["body"] == TASK_BODY
        assert page["tags"] == ["rollout"] and link("bench-decision") in page["links"]
    if scenario in {"decision", "recover"}:
        event = "bench-decision" if scenario == "decision" else "recover-fixture"
        rows, errors = load_entries(brain, sorted({now.date(), datetime.now(timezone.utc).date()}))
        assert not errors and sum(row["event_id"] == event for row in rows) == 1


async def measure(executable, root, now, current, log_file):
    brain, config = seed(root, now)
    command = [
        str(executable),
        "-I",
        "-X",
        "utf8",
        "-m",
        "second_brain.cli",
        "--config",
        str(config),
    ]
    transport = StdioTransport(command[0], [*command[1:], "serve"], env=ENV, log_file=log_file)
    measurements = {}
    async with viewer(command) as origin, Client(transport, timeout=30) as client:
        for operation in (resume, find_command, decision, edit, recover):
            flow = Flow(client, command, origin, current)
            started = perf_counter()
            error = None
            try:
                await operation(flow)
            except Exception as failure:
                error = type(failure).__name__
            elapsed = (perf_counter() - started) * 1000
            if error is None:
                try:
                    verify_writes(brain, now, operation.__name__)
                except Exception as failure:
                    error = type(failure).__name__
            measurements[operation.__name__] = dict(
                **flow.counts,
                elapsed_ms=round(elapsed, 2),
                success=error is None,
                error=error,
            )
    return measurements


async def compare(baseline, candidate, repeats):
    runs = {"baseline": [], "candidate": []}
    with tempfile.TemporaryDirectory(prefix="shiori-agent-efficiency-") as directory:
        root = Path(directory)
        for repeat in range(repeats):
            now = datetime.now(timezone.utc).replace(microsecond=0)
            order = ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
            for name in order:
                current = name == "candidate"
                runs[name].append(
                    await measure(
                        candidate if current else baseline,
                        root / f"{name}-{repeat}",
                        now,
                        current,
                        root / f"{name}-{repeat}.log",
                    )
                )
    summary = {}
    for name, samples in runs.items():
        summary[name] = {}
        for operation in samples[0]:
            rows = [sample[operation] for sample in samples]
            summary[name][operation] = {
                "passed": sum(row["success"] for row in rows),
                **{
                    f"median_{key}": median(row[key] for row in rows)
                    for key in rows[0]
                    if key not in {"success", "error"}
                },
            }
    passed = all(row["passed"] == repeats for group in summary.values() for row in group.values())
    print(json.dumps(dict(passed=passed, repeats=repeats, summary=summary, runs=runs), indent=2))
    return passed


def main():
    if not __debug__:
        raise SystemExit("Run without Python optimization so scenario checks stay enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-python", type=Path, required=True)
    parser.add_argument("--candidate-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--repeats", type=int, choices=range(1, 11), default=3)
    args = parser.parse_args()
    baseline = Path(os.path.abspath(args.baseline_python))
    candidate = Path(os.path.abspath(args.candidate_python))
    if not baseline.is_file() or not candidate.is_file():
        parser.error("Both Python interpreters must exist")
    if baseline == candidate:
        parser.error("Use separate installed baseline and candidate interpreters")
    if not asyncio.run(compare(baseline, candidate, args.repeats)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
