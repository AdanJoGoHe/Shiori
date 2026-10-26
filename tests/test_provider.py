import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from second_brain import provider


@pytest.mark.parametrize("platform, name", [("nt", "basic-memory.exe"), ("posix", "basic-memory")])
def test_provider_uses_current_environment_scripts(tmp_path, monkeypatch, platform, name):
    python = tmp_path / "venv/bin/python"
    monkeypatch.setattr(provider, "os", SimpleNamespace(name=platform))
    monkeypatch.setattr(provider, "sys", SimpleNamespace(executable=str(python)))
    assert provider.executable() == python.with_name(name)


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    config = {
        "vault_path": str(tmp_path / "vault"),
        "basic_memory_config_dir": str(tmp_path / "bm"),
    }
    settings = Path(config["basic_memory_config_dir"]) / "config.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {"projects": {"second-brain-personal": {"path": config["vault_path"], "mode": "local"}}}
        )
    )
    process = SimpleNamespace(returncode=0)
    response = SimpleNamespace(
        is_error=False,
        content=[SimpleNamespace(text='{"results": [{"file_path": "knowledge/a.md"}]}')],
    )

    async def wait():
        return process.returncode

    async def spawn(command, *args, **kwargs):
        assert Path(command).name in {"basic-memory", "basic-memory.exe"}
        assert args == ("reindex", "--search", "--project", "second-brain-personal")
        assert kwargs["env"]["BASIC_MEMORY_HOME"] == config["vault_path"]
        assert kwargs["env"]["BASIC_MEMORY_CLOUD_MODE"] == "false"
        assert "BASIC_MEMORY_PROJECTS" not in kwargs["env"]
        return process

    class Client:
        def __init__(self, transport):
            server = transport["mcpServers"]["memory"]
            assert server["args"] == ["mcp", "--project", "second-brain-personal"]
            assert server["env"] == provider.environment(config)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def call_tool(self, name, arguments):
            assert name == "search_notes"
            assert arguments["page_size"] == 5
            assert arguments["project"] == "second-brain-personal"
            return response

    process.wait = wait
    monkeypatch.setattr(provider.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(provider, "Client", Client)
    return config, process, response


@pytest.mark.parametrize("failure", ["missing", "json", "cloud", "other-vault", "extra-project"])
def test_provider_configuration_must_be_isolated_before_launch(adapter, monkeypatch, failure):
    config, _, _ = adapter
    path = Path(config["basic_memory_config_dir"]) / "config.json"
    settings = json.loads(path.read_text())
    if failure == "missing":
        path.unlink()
    elif failure == "json":
        path.write_text("password=synthetic-private-output")
    else:
        project = settings["projects"]["second-brain-personal"]
        if failure == "cloud":
            project["mode"] = "cloud"
        elif failure == "other-vault":
            project["path"] = str(path.parent / "other-vault")
        else:
            settings["projects"]["another"] = dict(project)
        path.write_text(json.dumps(settings))

    async def unexpected(*args, **kwargs):
        raise AssertionError("Invalid provider configuration must not launch a process")

    monkeypatch.setattr(provider.asyncio, "create_subprocess_exec", unexpected)
    with pytest.raises(provider.ProviderUnavailable, match="invalid-configuration"):
        asyncio.run(provider.provider_search(config, "query"))


def test_provider_result_contract_and_disabled_features(adapter, monkeypatch):
    config, _, _ = adapter
    monkeypatch.setenv("BASIC_MEMORY_CLOUD_MODE", "true")
    monkeypatch.setenv("BASIC_MEMORY_PROJECTS", '{"other": "/synthetic-other-vault"}')
    assert asyncio.run(provider.provider_search(config, "query")) == [
        {"file_path": "knowledge/a.md"}
    ]
    env = provider.environment(config)
    for name in ["CLOUD_MODE", "SEMANTIC_SEARCH_ENABLED", "LOGFIRE_ENABLED", "AUTO_UPDATE"]:
        assert env[f"BASIC_MEMORY_{name}"] == "false"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"results": {}},
        {"results": [None]},
        {"results": [{"file_path": 1}]},
        {"results": [{"file_path": "a"}] * 6},
    ],
)
def test_malformed_provider_payload_is_controlled(adapter, payload):
    config, _, response = adapter
    response.content[0].text = json.dumps(payload)
    with pytest.raises(provider.ProviderUnavailable, match="invalid-response"):
        asyncio.run(provider.provider_search(config, "query"))


@pytest.mark.parametrize("failure", ["reindex", "search", "json", "missing-text", "configuration"])
def test_provider_failures_do_not_echo_output(adapter, failure):
    config, process, response = adapter
    expected = "invalid-response"
    if failure == "reindex":
        process.returncode = 1
        expected = "reindex-failed"
    elif failure == "search":
        response.is_error = True
        expected = "search-failed"
    elif failure == "json":
        response.content[0].text = "password=synthetic-private-output"
    elif failure == "missing-text":
        response.content = []
    else:
        config.pop("basic_memory_config_dir")
        expected = "not-configured"
    with pytest.raises(provider.ProviderUnavailable) as error:
        asyncio.run(provider.provider_search(config, "query"))
    assert str(error.value) == expected


def test_cancelled_reindex_is_killed_and_reaped(adapter):
    config, process, _ = adapter

    async def scenario():
        started = asyncio.Event()
        waits = []
        process.returncode = None

        async def wait():
            waits.append(True)
            started.set()
            if process.returncode is None:
                await asyncio.Event().wait()
            return process.returncode

        def kill():
            process.returncode = -1

        process.wait = wait
        process.kill = kill
        task = asyncio.create_task(provider.provider_search(config, "query"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.returncode == -1 and len(waits) == 2

    asyncio.run(scenario())


@pytest.fixture
def probe(adapter, monkeypatch):
    config, process, _ = adapter
    reply = SimpleNamespace(
        raw=b'{"total_files": 1, "observed_files": [{"path": "private-path.md"}]}',
        error=None,
        spawn_error=None,
        code=0,
        spawned=0,
        killed=False,
    )

    class Stream:
        async def readexactly(self, limit):
            assert limit == 1024 * 1024 + 1
            if reply.error:
                raise reply.error
            if len(reply.raw) >= limit:
                return reply.raw[:limit]
            raise asyncio.IncompleteReadError(reply.raw, limit)

    async def spawn(command, *args, **kwargs):
        reply.spawned += 1
        if reply.spawn_error:
            raise reply.spawn_error
        assert args == ("status", "--project", "second-brain-personal", "--json", "--local")
        assert "BASIC_MEMORY_PROJECTS" not in kwargs["env"]
        process.returncode = None if reply.error or len(reply.raw) > 1024 * 1024 else reply.code
        process.stdout = Stream()
        return process

    def kill():
        reply.killed = True
        process.returncode = -1

    process.kill = kill
    monkeypatch.setattr(provider.asyncio, "create_subprocess_exec", spawn)
    return config, reply


def test_live_probe_returns_only_availability_and_count(probe, monkeypatch):
    config, reply = probe
    monkeypatch.setenv("BASIC_MEMORY_PROJECTS", "synthetic-unapproved-project")
    result = asyncio.run(provider.probe_provider(config))
    assert result == {"status": "available", "check": "project-status", "total_files": 1}
    assert "private-path" not in str(result)
    assert reply.spawned == 1 and not reply.killed


@pytest.mark.parametrize(
    "raw",
    [
        b"password=synthetic-private-output",
        b"{}",
        b'{"total_files": true, "observed_files": []}',
        b'{"total_files": -1, "observed_files": []}',
        b'{"total_files": 1, "observed_files": []}',
        b'{"total_files": 0, "observed_files": {}}',
        b'{"total_files": 1, "observed_files": [{"path": 1}]}',
        b"x" * (1024 * 1024 + 1),
        b"[" * 2000 + b"]" * 2000,
    ],
    ids=[
        "not-json",
        "missing",
        "bool-count",
        "negative",
        "mismatch",
        "not-list",
        "bad-path",
        "oversized",
        "nested",
    ],
)
def test_live_probe_rejects_invalid_or_oversized_status(probe, raw):
    config, reply = probe
    reply.raw = raw
    result = asyncio.run(provider.probe_provider(config))
    assert result == {
        "status": "unavailable",
        "check": "project-status",
        "reason": "invalid-response",
    }
    assert reply.killed == (len(raw) > 1024 * 1024)


def test_live_probe_failed_process_has_no_raw_error(probe):
    config, reply = probe
    reply.code = 1
    reply.raw = b'{"error": "password=synthetic-private-output"}'
    assert asyncio.run(provider.probe_provider(config))["reason"] == "status-failed"


def test_live_probe_not_configured_does_not_spawn(probe):
    config, reply = probe
    config.pop("basic_memory_config_dir")
    assert asyncio.run(provider.probe_provider(config))["reason"] == "not-configured"
    assert reply.spawned == 0


@pytest.mark.parametrize(
    "error, reason",
    [
        (FileNotFoundError("private-path"), "executable-not-found"),
        (PermissionError("password=synthetic-private-output"), "provider-error"),
    ],
)
def test_live_probe_spawn_failure_has_bounded_reason(probe, error, reason):
    config, reply = probe
    reply.spawn_error = error
    assert asyncio.run(provider.probe_provider(config)) == {
        "status": "unavailable",
        "check": "project-status",
        "reason": reason,
    }


def test_live_probe_timeout_and_cancellation_reap_child(probe):
    config, reply = probe
    reply.error = TimeoutError("password=synthetic-private-output")
    assert asyncio.run(provider.probe_provider(config))["reason"] == "timeout"
    assert reply.killed
    reply.killed = False
    reply.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider.probe_provider(config))
    assert reply.killed
