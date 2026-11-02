"""Shared constants for database tests (overridable via environment variables)."""

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent

TEST_OWNER_URL = os.environ.get(
    "UNICODE_TEST_OWNER_URL",
    "postgresql://unicode_owner:unicode_owner@localhost:5432/unicode_test",
)
TEST_DAEMON_URL = os.environ.get(
    "UNICODE_TEST_DAEMON_URL",
    "postgresql://unicode_daemon:unicode_daemon@localhost:5432/unicode_test",
)
TEST_PANEL_URL = os.environ.get(
    "UNICODE_TEST_PANEL_URL",
    "postgresql://unicode_panel:unicode_panel@localhost:5432/unicode_test",
)


def alembic_config(url: str) -> Config:
    """Alembic config pointing at `url` (used by tests to migrate unicode_test)."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


class AsgiResponse:
    """Lightweight response returned by AsgiTestClient."""

    def __init__(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self.content = body

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.text)


class AsgiTestClient:
    """Minimal in-memory ASGI 3.0 HTTP client for testing FastAPI without httpx."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        basic_auth: tuple[str, str] | None = None,
    ) -> AsgiResponse:
        req_headers: dict[str, str] = {}
        if headers:
            for k, v in headers.items():
                req_headers[k.lower()] = v
        if basic_auth is not None:
            raw = f"{basic_auth[0]}:{basic_auth[1]}".encode()
            token = base64.b64encode(raw).decode("ascii")
            req_headers["authorization"] = f"Basic {token}"

        parts = urlsplit(path)
        raw_headers = [
            (k.encode("latin-1"), v.encode("latin-1")) for k, v in req_headers.items()
        ]

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": parts.path or "/",
            "raw_path": (parts.path or "/").encode("ascii"),
            "query_string": parts.query.encode("ascii"),
            "headers": raw_headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }

        status_code = 500
        resp_headers: dict[str, str] = {}
        body_chunks: list[bytes] = []
        response_complete = asyncio.Event()
        request_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await response_complete.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal status_code, resp_headers
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                resp_headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                }
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    response_complete.set()

        asyncio.run(self.app(scope, receive, send))
        return AsgiResponse(status_code, resp_headers, b"".join(body_chunks))

