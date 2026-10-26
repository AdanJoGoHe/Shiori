"""Opt-in authenticated MCP foundation; network ingress remains a separate deployment."""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path

from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware
from starlette.middleware import Middleware as HTTPMiddleware
from starlette.responses import PlainTextResponse

from second_brain.core import SLUG, canonical_root

READ_TOOLS = frozenset(
    {
        "search_memory",
        "get_context",
        "read_memory",
        "classify_memory",
        "list_content",
        "list_pending_captures",
        "memory_status",
    }
)
MAX_REQUEST = 64_000
BODY_TIMEOUT = 10


def proxy_hosts(authority):
    """Allow one explicit HTTPS authority, never wildcard or forwarded-header trust."""
    if authority is None:
        return ()
    if not isinstance(authority, str):
        raise ValueError("Proxy Host requires a DNS name with an optional HTTPS port")
    authority = authority.lower()
    host, separator, port = authority.partition(":")
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if (
        len(host) > 253
        or not re.fullmatch(rf"{label}(?:\.{label})+", host)
        or not re.search(r"[a-z]", host.rsplit(".", 1)[-1])
        or (separator and (not re.fullmatch(r"[1-9][0-9]{0,4}", port) or int(port) > 65535))
    ):
        raise ValueError("Proxy Host requires a DNS name with an optional HTTPS port")
    if not separator or port == "443":
        return (host, host + ":443")
    return (authority,)


class Credentials(TokenVerifier):
    def __init__(self, path, config):
        super().__init__(required_scopes=["memory:read"])
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError("Credentials require an absolute private file path")
        roots = [config["vault_path"], *config.get("documentation_roots", {}).values()]
        if any(self.path.resolve().is_relative_to(canonical_root(root)) for root in roots):
            raise ValueError("Credentials must stay outside readable content roots")
        self.load()

    def load(self):
        try:
            if not self.path.is_file():
                raise ValueError
            if any(p.is_symlink() or p.is_junction() for p in [self.path, *self.path.parents]):
                raise ValueError
            with self.path.open("rb") as stream:
                raw = stream.read(64_001)
            if len(raw) > 64_000:
                raise ValueError
            data = json.loads(raw)
            if (
                not isinstance(data, dict)
                or set(data) != {"schema_version", "clients"}
                or type(data["schema_version"]) is not int
                or data["schema_version"] != 1
                or not isinstance(data["clients"], list)
                or len(data["clients"]) > 64
            ):
                raise ValueError
            ids, hashes = set(), set()
            for row in data["clients"]:
                if (
                    not isinstance(row, dict)
                    or set(row) != {"id", "token_sha256", "permission", "expires_at"}
                    or not isinstance(row["id"], str)
                    or not SLUG.fullmatch(row["id"])
                    or not isinstance(row["token_sha256"], str)
                    or not re.fullmatch(r"[a-f0-9]{64}", row["token_sha256"])
                    or row["permission"] not in ("read", "write")
                    or type(row["expires_at"]) is not int
                    or row["expires_at"] < 0
                    or row["id"] in ids
                    or row["token_sha256"] in hashes
                ):
                    raise ValueError
                ids.add(row["id"])
                hashes.add(row["token_sha256"])
            return data["clients"]
        except (OSError, ValueError, TypeError, RecursionError):
            raise ValueError("Credentials registry is unavailable or invalid") from None

    async def verify_token(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
            return None
        try:
            rows = self.load()  # Re-read on every request: removal/expiry revokes existing clients.
        except ValueError:
            return None
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        for row in rows:
            if hmac.compare_digest(digest, row["token_sha256"]) and row["expires_at"] > time.time():
                scopes = ["memory:read"] + (
                    ["memory:write"] if row["permission"] == "write" else []
                )
                return AccessToken(
                    token=token,
                    client_id=row["id"],
                    subject=row["id"],
                    scopes=scopes,
                    expires_at=row["expires_at"],
                )
        return None


class RemotePolicy(Middleware):
    async def on_call_tool(self, context, call_next):
        token = get_access_token()
        name = context.message.name
        permitted = (
            token is not None
            and "memory:read" in token.scopes
            and (
                name in READ_TOOLS or (name == "capture_memory" and "memory:write" in token.scopes)
            )
        )
        if not permitted:
            raise ToolError("Tool is not available for this credential")
        try:
            return await call_next(context)
        except Exception:
            raise ToolError("Memory operation failed") from None

    async def on_list_tools(self, context, call_next):
        token = get_access_token()
        if token is None or "memory:read" not in token.scopes:
            return []
        allowed = READ_TOOLS | ({"capture_memory"} if "memory:write" in token.scopes else set())
        return [tool for tool in await call_next(context) if tool.name in allowed]


class RequestBoundary:
    def __init__(self, app, proxy_host=None):
        self.app = app
        self.proxy_hosts = proxy_hosts(proxy_host)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope["headers"]

        def values(name):
            return [v.decode("latin-1") for k, v in headers if k.lower() == name]

        hosts = values(b"host")
        code = None
        if len(values(b"authorization")) > 1 or scope.get("query_string"):
            code = 400
        if (
            len(hosts) != 1
            or not (
                re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?", hosts[0])
                or hosts[0].lower() in self.proxy_hosts
            )
            or values(b"origin")
            or values(b"sec-fetch-site") not in ([], ["none"])
        ):
            code = 403
        if scope["method"] == "POST" and code is None:
            lengths = values(b"content-length")
            if (
                len(lengths) != 1
                or not re.fullmatch(r"[0-9]{1,8}", lengths[0])
                or values(b"transfer-encoding")
            ):
                code = 400
            elif int(lengths[0]) > MAX_REQUEST:
                code = 413
            else:
                body = bytearray()
                deadline = time.monotonic() + BODY_TIMEOUT
                while True:
                    try:
                        message = await asyncio.wait_for(
                            receive(), max(0.001, deadline - time.monotonic())
                        )
                    except TimeoutError:
                        code = 408
                        break
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > MAX_REQUEST:
                        code = 413
                        break
                    if not message.get("more_body"):
                        break
                if code is None and len(body) != int(lengths[0]):
                    code = 400
                if code is None:
                    original_receive = receive
                    delivered = False

                    async def buffered():
                        nonlocal delivered
                        if delivered:
                            return await original_receive()
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}

                    receive = buffered
        if code is not None:
            return await PlainTextResponse("Request rejected", status_code=code)(
                scope, receive, send
            )

        async def safe_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        await self.app(scope, receive, safe_send)


def create_remote_server(config, credentials_file):
    from second_brain.server import create_server

    credentials = Credentials(
        credentials_file, config
    )  # Validate before Brain can initialize roots.
    return create_server(config, auth=credentials, middleware=[RemotePolicy()])


def serve_http(config, credentials_file, port=8794, proxy_host=None):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Choose a port between 1 and 65535")
    external_hosts = proxy_hosts(proxy_host)
    server = create_remote_server(config, credentials_file)
    sdk_log = logging.getLogger("mcp")
    previous_level = sdk_log.level
    sdk_log.setLevel(logging.CRITICAL)
    try:
        server.run(
            transport="http",
            host="127.0.0.1",
            port=port,
            path="/mcp",
            show_banner=False,
            stateless_http=True,
            json_response=True,
            host_origin_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", *external_hosts],
            allowed_origins=[],
            middleware=[HTTPMiddleware(RequestBoundary, proxy_host=proxy_host)],
            log_level="critical",
            uvicorn_config={
                "access_log": False,
                "proxy_headers": False,
                "server_header": False,
                "limit_concurrency": 16,
                "timeout_keep_alive": 5,
                "ws": "none",
            },
        )
    except SystemExit as error:
        if error.code:
            raise ValueError(
                "Remote MCP could not start; check configuration and selected port"
            ) from None
    finally:
        sdk_log.setLevel(previous_level)
