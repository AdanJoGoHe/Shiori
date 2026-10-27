import asyncio
import hashlib
import json
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import httpx
import pytest
from starlette.middleware import Middleware
import uvicorn

from second_brain.remote import (
    Credentials,
    RequestBoundary,
    create_remote_server,
    proxy_hosts,
    serve_http,
)
from test_core import brain as brain, event

READER = "synthetic-reader-" + "a" * 43
WRITER = "synthetic-writer-" + "b" * 43


def registry(path, *, reader=True, writer=True, expires=None):
    rows = [
        {
            "id": name,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "permission": permission,
            "expires_at": expires if expires is not None else int(time.time()) + 3600,
        }
        for name, token, permission, enabled in [
            ("reader", READER, "read", reader),
            ("writer", WRITER, "write", writer),
        ]
        if enabled
    ]
    path.write_text(json.dumps({"schema_version": 1, "clients": rows}), encoding="utf-8")


@pytest.fixture
def remote(brain, tmp_path, request):
    credentials = tmp_path / "credentials.json"
    registry(credentials)
    mcp = create_remote_server(brain.config, credentials)
    proxy_host = getattr(request, "param", None)
    app = mcp.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=["127.0.0.1:*", *proxy_hosts(proxy_host)],
        allowed_origins=[],
        middleware=[Middleware(RequestBoundary, proxy_host=proxy_host)],
    )
    sock = socket.socket()
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="critical",
            access_log=False,
            proxy_headers=False,
            ws="none",
            lifespan="on",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        yield url, credentials, brain
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


def test_real_http_roles_shared_store_idempotency_and_revocation(remote):
    url, credentials, brain = remote

    async def scenario():
        async with Client(url, auth=READER) as reader, Client(url, auth=WRITER) as writer:
            assert "capture_memory" not in {t.name for t in await reader.list_tools()}
            assert len(await writer.list_tools()) == 9
            assert len(await reader.list_tools()) == 8  # No cross-client permission cache.
            before = brain.ledger_path.read_bytes() if brain.ledger_path.exists() else None
            denied = await reader.call_tool(
                "capture_memory", {"candidate": event()}, raise_on_error=False
            )
            assert denied.is_error
            assert (
                brain.ledger_path.read_bytes() if brain.ledger_path.exists() else None
            ) == before
            assert not list(brain.vault.rglob("*.md"))
            assert (await writer.call_tool("capture_memory", {"candidate": event()})).data[
                "status"
            ] == "saved"
            assert (await writer.call_tool("capture_memory", {"candidate": event()})).data[
                "status"
            ] == "duplicate"
            assert (await reader.call_tool("get_context", {"query": "Git"})).data["notes"][0][
                "id"
            ] == "git-version"
            found = (await reader.call_tool("search_memory", {"query": "Git"})).data
            assert found["provider"] == "filesystem"
            assert found["ranking"] == "canonical-text" and "index_status" not in found
            assert (await reader.call_tool("read_memory", {"note_id": "git-version"})).data
            assert (await reader.call_tool("list_content", {"kind": "note"})).data["items"]
            assert (await reader.call_tool("list_pending_captures", {})).data["total"] == 0
            assert (await reader.call_tool("read_journal", {})).data["total"] == 1
            assert (await reader.call_tool("memory_status", {})).data["notes"] == 1
            assert "vault" not in (await reader.call_tool("memory_status", {})).data
            classification = await reader.call_tool(
                "classify_memory",
                {
                    "candidate": event(),
                    "assessment": {
                        "material": "personal",
                        "reusable": True,
                        "meaningful": True,
                        "evidence_kind": "observed",
                    },
                },
            )
            assert classification.data["decision"] in {"skip", "update"}
            unsafe = await reader.call_tool(
                "read_memory", {"note_id": "../SYNTHETIC-PRIVATE"}, raise_on_error=False
            )
            assert unsafe.is_error and "SYNTHETIC-PRIVATE" not in str(unsafe)
            work = await writer.call_tool("capture_memory", {"candidate": event(scope="work")})
            assert work.data == {"status": "failed", "reason": "capture-failed"}
            registry(credentials, reader=False)
            with pytest.raises(Exception):
                await reader.call_tool("memory_status", {})
            assert (await writer.call_tool("memory_status", {})).data["notes"] == 1
            reduced = json.loads(credentials.read_text(encoding="utf-8"))
            reduced["clients"][0]["permission"] = "read"
            credentials.write_text(json.dumps(reduced), encoding="utf-8")
            assert len(await writer.list_tools()) == 8
            denied = await writer.call_tool(
                "capture_memory",
                {"candidate": event(event_id="permission-reduced")},
                raise_on_error=False,
            )
            assert denied.is_error
            credentials.write_text("{broken", encoding="utf-8")
            with pytest.raises(Exception):
                await writer.call_tool("memory_status", {})
        registry(credentials)
        # Fresh connection sees persisted memory, not client-local state.
        async with Client(url, auth=WRITER) as writer:
            assert (await writer.call_tool("capture_memory", {"candidate": event()})).data[
                "status"
            ] == "duplicate"

    asyncio.run(scenario())


def test_http_missing_wrong_expired_credentials_host_origin_and_limits(remote):
    url, credentials, brain = remote
    original = {
        p: p.read_bytes()
        for root in [brain.vault, brain.state]
        for p in root.rglob("*")
        if p.is_file()
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "synthetic", "version": "1"},
        },
    }
    headers = {"Authorization": "Bearer " + READER, "Accept": "application/json, text/event-stream"}
    with httpx.Client(trust_env=False) as client:
        for auth in [None, "Bearer invalid", "Bearer " + "z" * 43]:
            h = {**headers}
            if auth is None:
                del h["Authorization"]
            else:
                h["Authorization"] = auth
            assert client.post(url, json=payload, headers=h).status_code == 401
        for extra, expected in [
            ({"Host": "attacker.test"}, 421),
            ({"Origin": "https://attacker.test"}, 403),
            ({"Origin": url.rsplit("/", 1)[0]}, 403),
            ({"Sec-Fetch-Site": "same-site"}, 403),
        ]:
            assert (
                client.post(url, json=payload, headers={**headers, **extra}).status_code == expected
            )
        oversized = client.post(url, content=b"x" * 64_001, headers=headers)
        assert oversized.status_code == 413
        assert (
            client.post(url + "?token=not-accepted", json=payload, headers=headers).status_code
            == 400
        )
        registry(credentials, expires=1)
        assert client.post(url, json=payload, headers=headers).status_code == 401
    assert all(p.read_bytes() == raw for p, raw in original.items())


def test_concurrent_http_writers_dedupe_one_event(remote):
    url, _, brain = remote

    async def capture():
        async with Client(url, auth=WRITER) as client:
            return (await client.call_tool("capture_memory", {"candidate": event()})).data["status"]

    async def scenario():
        return await asyncio.gather(capture(), capture())

    assert sorted(asyncio.run(scenario())) == ["duplicate", "saved"]
    assert brain.status()["notes"] == 1
    assert (
        next(brain.vault.glob("journal/*/*.md"))
        .read_text(encoding="utf-8")
        .count("<!-- event:test-event -->")
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        None,
        {},
        {"clients": "wrong"},
        {"schema_version": True},
        {"clients": [{"id": "x", "token_sha256": "bad", "permission": "write", "expires_at": 1}]},
    ],
)
def test_invalid_registry_never_initializes_store(tmp_path, change):
    path = tmp_path / "credentials.json"
    if change is not None:
        path.write_text(
            json.dumps({"schema_version": 1, "clients": [], **change}), encoding="utf-8"
        )
        if change == {}:
            path.write_bytes(b"x" * 64_001)
    config = {
        "scope": "personal",
        "vault_path": str(tmp_path / "vault"),
        "state_path": str(tmp_path / "state"),
        "timezone": "Europe/Madrid",
    }
    with pytest.raises(ValueError, match="Credentials"):
        create_remote_server(config, path)
    assert not (tmp_path / "vault").exists() and not (tmp_path / "state").exists()


def test_credentials_outside_content_roots_and_duplicate_registry(brain, tmp_path):
    for path in [brain.vault / "credentials.json", tmp_path / "docs" / "credentials.json"]:
        config = {**brain.config, "documentation_roots": {"docs": str(tmp_path / "docs")}}
        with pytest.raises(ValueError, match="outside"):
            Credentials(path, config)
    path = tmp_path / "credentials.json"
    registry(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["clients"].append(data["clients"][0])
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Credentials"):
        Credentials(path, brain.config)
    with pytest.raises(ValueError, match="port"):
        serve_http(brain.config, path, 0)


def test_http_launcher_stays_loopback_and_disables_request_logs(monkeypatch):
    import second_brain.remote as remote

    runs = []
    monkeypatch.setattr(
        remote,
        "create_remote_server",
        lambda config, path: SimpleNamespace(run=lambda **kw: runs.append(kw)),
    )
    serve_http({}, "synthetic-registry", 8794)
    assert runs[0]["host"] == "127.0.0.1"
    assert runs[0]["stateless_http"] and runs[0]["host_origin_protection"]
    assert runs[0]["uvicorn_config"]["access_log"] is False
    assert runs[0]["uvicorn_config"]["proxy_headers"] is False


@pytest.mark.parametrize(
    "headers,body,expected",
    [
        ([(b"content-length", b"2")], b"{}", None),
        ([], b"{}", 400),
        ([(b"content-length", b"1")], b"{}", 400),
        ([(b"content-length", b"2"), (b"content-length", b"2")], b"{}", 400),
        ([(b"content-length", b"2"), (b"transfer-encoding", b"chunked")], b"{}", 400),
        ([(b"content-length", b"2")], b"x" * 64_001, 413),
        (
            [(b"content-length", b"2"), (b"authorization", b"a"), (b"authorization", b"b")],
            b"{}",
            400,
        ),
    ],
    ids=[
        "valid",
        "missing-length",
        "wrong-length",
        "duplicate-length",
        "chunked",
        "body-too-large",
        "duplicate-auth",
    ],
)
def test_request_boundary_actual_body_and_duplicate_headers(headers, body, expected):
    called, messages = [], []

    async def inner(scope, receive, send):
        called.append(True)
        assert (await receive())["body"] == b"{}"

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        RequestBoundary(inner)(
            {"type": "http", "method": "POST", "headers": [(b"host", b"127.0.0.1:8794"), *headers]},
            receive,
            send,
        )
    )
    if expected is None:
        assert called == [True]
    else:
        assert not called and messages[0]["status"] == expected


def test_unknown_future_tool_is_denied_even_to_writer(remote):
    url, _, _ = remote

    async def scenario():
        async with Client(url, auth=WRITER) as client:
            result = await client.call_tool("future_write", {}, raise_on_error=False)
            assert result.is_error

    asyncio.run(scenario())


@pytest.mark.parametrize("proxy_host", [None, "memory.example.test:8443"])
def test_real_cli_process_no_credentials_or_tool_content_in_logs(brain, tmp_path, proxy_host):
    credentials = tmp_path / "credentials.json"
    registry(credentials)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({**brain.config, "schema_version": 1}), encoding="utf-8")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    command = [
        sys.executable,
        "-m",
        "second_brain.cli",
        "--config",
        str(config),
        "serve-http",
        "--credentials-file",
        str(credentials),
        "--port",
        str(port),
    ]
    if proxy_host:
        command.extend(["--proxy-host", proxy_host])
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        with httpx.Client(trust_env=False, timeout=0.5) as client:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None
                try:
                    if (
                        client.post(
                            url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
                        ).status_code
                        == 401
                    ):
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline
                time.sleep(0.05)

        async def scenario():
            transport = StreamableHttpTransport(
                url, headers={"Host": proxy_host} if proxy_host else None
            )
            async with Client(transport, auth=READER) as reader:
                assert len(await reader.list_tools()) == 8
                bad = await reader.call_tool(
                    "get_context",
                    {"query": "CLI-PRIVATE-SENTINEL", "max_chars": "INVALID-PRIVATE-SENTINEL"},
                    raise_on_error=False,
                )
                assert bad.is_error
                assert "PRIVATE-SENTINEL" not in str(bad)
                assert (await reader.call_tool("memory_status", {})).data["notes"] == 0

        asyncio.run(scenario())
    finally:
        process.terminate()  # Only this fixture's child; never terminate a port occupant.
        output, errors = process.communicate(timeout=10)
    for value in [READER, WRITER, "PRIVATE-SENTINEL"]:
        assert value.encode() not in output + errors


def test_request_body_timeout_denies_before_app(monkeypatch):
    import second_brain.remote as remote

    monkeypatch.setattr(remote, "BODY_TIMEOUT", 0.01)
    messages = []

    async def inner(*args):
        pytest.fail("Timed out request reached the app")

    async def receive():
        await asyncio.sleep(1)

    async def send(message):
        messages.append(message)

    asyncio.run(
        RequestBoundary(inner)(
            {
                "type": "http",
                "method": "POST",
                "headers": [(b"host", b"127.0.0.1:8794"), (b"content-length", b"2")],
            },
            receive,
            send,
        )
    )
    assert messages[0]["status"] == 408


def test_exact_proxy_authority_validation_and_launcher(monkeypatch):
    import second_brain.remote as remote

    assert proxy_hosts(None) == ()
    assert proxy_hosts("Memory.Example.Test") == ("memory.example.test", "memory.example.test:443")
    assert proxy_hosts("memory.example.test:443") == proxy_hosts("memory.example.test")
    assert proxy_hosts("memory.example.test:8443") == ("memory.example.test:8443",)
    for invalid in [
        "",
        "*",
        "*.ts.net",
        "https://memory.example.test",
        "memory.example.test/mcp",
        "memory.example.test?token=x",
        "user@memory.example.test",
        "127.0.0.1",
        "localhost",
        "memory.example.test.",
        "memory.example.test:0",
        "memory.example.test:65536",
        "memory.example.test:0443",
        "memory.example.test:",
        "memory.example.test:443:443",
        "memory.example.test\r\nX: y",
        "-bad.example.test",
        "éxample.test",
        443,
    ]:
        with pytest.raises(ValueError, match="Proxy Host"):
            # Validation must precede server/store initialization.
            serve_http({}, "does-not-exist", proxy_host=invalid)
    runs = []
    monkeypatch.setattr(
        remote,
        "create_remote_server",
        lambda *args: SimpleNamespace(run=lambda **kw: runs.append(kw)),
    )
    serve_http({}, "synthetic", proxy_host="memory.example.test:8443")
    assert runs[0]["host"] == "127.0.0.1"
    assert runs[0]["allowed_hosts"] == ["127.0.0.1:*", "localhost:*", "memory.example.test:8443"]
    assert not runs[0]["uvicorn_config"]["proxy_headers"]


@pytest.mark.parametrize("remote", ["memory.example.test:8443"], indirect=True)
def test_verified_tls_proxy_preserves_host_auth_roles_and_revocation(remote, tmp_path):
    """Synthetic TLS hop, not a Tailscale or second-device acceptance test."""
    import datetime
    import ipaddress
    import ssl
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    backend, credentials, brain = remote
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-loopback")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certfile, keyfile = tmp_path / "test.pem", tmp_path / "test-key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    class Proxy(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(min(int(self.headers["Content-Length"]), 64_001))
            headers = dict(self.headers)
            # Treat these as untrusted assertions even when the proxy sends them.
            headers.update({"X-Forwarded-Proto": "https", "Tailscale-User-Login": "synthetic"})
            with httpx.Client(trust_env=False, timeout=10) as client:
                response = client.post(
                    backend.replace("/mcp", self.path), content=body, headers=headers
                )
            self.send_response(response.status_code)
            for field in ["content-type", "cache-control"]:
                if field in response.headers:
                    self.send_header(field, response.headers[field])
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        def log_message(self, *args):
            pass

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certfile, keyfile)
    proxy.socket = tls.wrap_socket(proxy.socket, server_side=True)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    url = f"https://127.0.0.1:{proxy.server_port}/mcp"
    trusted = ssl.create_default_context(cafile=str(certfile))
    host = {"Host": "memory.example.test:8443"}
    try:
        with httpx.Client(trust_env=False, timeout=10) as client:
            with pytest.raises(httpx.ConnectError):
                client.post(url, json={})  # Untrusted certificate is not silently accepted.
        with httpx.Client(trust_env=False, verify=trusted, timeout=10) as client:
            with pytest.raises(httpx.ConnectError):
                client.post(url.replace("127.0.0.1", "localhost"), json={})
            assert client.post(url, json={}, headers=host).status_code == 401
            auth = {**host, "Authorization": "Bearer " + READER}
            for bad in [
                {"Host": "other.example.test:8443"},
                {"Host": "memory.example.test:443"},
                {"Origin": "https://memory.example.test:8443"},
                {"Origin": "https://other.example.test"},
                {"Sec-Fetch-Site": "same-origin"},
            ]:
                assert client.post(url, json={}, headers={**auth, **bad}).status_code in {403, 421}
            assert client.post(url + "?token=synthetic", json={}, headers=auth).status_code == 400
            assert client.post(url, content=b"x" * 64_001, headers=auth).status_code == 413
            for path in ["/", "/viewer", "/admin"]:
                assert (
                    client.post(url.replace("/mcp", path), json={}, headers=auth).status_code == 404
                )
            # Spoofed forwarding metadata cannot grant an unconfigured authority.
            assert (
                client.post(
                    backend,
                    json={},
                    headers={
                        "Host": "other.example.test",
                        "X-Forwarded-Host": "memory.example.test:8443",
                        "Forwarded": "host=memory.example.test:8443;proto=https",
                        **{k: v for k, v in auth.items() if k != "Host"},
                    },
                ).status_code
                == 421
            )

        async def scenario():
            transport = StreamableHttpTransport(url, headers=host, verify=trusted)
            async with Client(transport, auth=READER) as reader:
                assert len(await reader.list_tools()) == 8
                denied = await reader.call_tool(
                    "capture_memory", {"candidate": event()}, raise_on_error=False
                )
                assert denied.is_error
                assert not list(brain.vault.rglob("*.md"))
                writer_transport = StreamableHttpTransport(url, headers=host, verify=trusted)
                async with Client(writer_transport, auth=WRITER) as writer:
                    assert len(await writer.list_tools()) == 9
                    assert (await writer.call_tool("capture_memory", {"candidate": event()})).data[
                        "status"
                    ] == "saved"
                assert (await reader.call_tool("search_memory", {"query": "Git"})).data[
                    "provider"
                ] == "filesystem"
                assert (await reader.call_tool("get_context", {"query": "Git"})).data["notes"][0][
                    "id"
                ] == "git-version"
                registry(credentials, reader=False)
                with pytest.raises(Exception):
                    await reader.call_tool("memory_status", {})

        asyncio.run(scenario())
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(10)
        assert not thread.is_alive()
