"""
End-to-end test for the /alerts/stream SSE endpoint (formerly exercised by
hand via the now-deleted backend/sse_smoke_test.ps1).

httpx's ASGITransport (used by the `client`/`plain_client` fixtures for every
other endpoint test) fully buffers a response - it awaits the whole ASGI app
call to completion before returning anything - so it can't be used here: this
endpoint intentionally streams forever until the client disconnects, which
would deadlock (the app never finishes, so httpx never gets a response, so it
never sends a disconnect). Instead this test drives the raw ASGI protocol
directly, with full control over when to signal `http.disconnect`.

The endpoint's own polling loop and this test both talk to the database
*concurrently* once the stream is running, so seeding goes through a second,
independently committed session/connection rather than the shared
rolled-back `db_session` fixture used elsewhere - a single AsyncSession isn't
safe for concurrent use. The seeded row is deleted in a `finally` block so
nothing is left behind in the real database.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.types import Message

from app.db.session import get_db
from app.main import app
from app.models.pipeline_alert import PipelineAlert

pytestmark = pytest.mark.db

TIMEOUT = 5.0


class _RawAsgiSseClient:
    """Drives `app(scope, receive, send)` directly for one streaming request."""

    def __init__(self, path: str, query_string: bytes = b""):
        self.scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query_string,
            "root_path": "",
            "headers": [(b"accept", b"text/event-stream")],
            "client": ("testclient", 1234),
            "server": ("testserver", 80),
        }
        self._body_sent = False
        self._disconnect = asyncio.Event()
        self._messages: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._buffer = ""

    async def _receive(self) -> Message:
        if not self._body_sent:
            self._body_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: Message) -> None:
        await self._messages.put(dict(message))

    def start(self) -> None:
        self._task = asyncio.create_task(app(self.scope, self._receive, self._send))

    async def read_start(self) -> dict[str, Any]:
        while True:
            message = await asyncio.wait_for(self._messages.get(), timeout=TIMEOUT)
            if message["type"] == "http.response.start":
                return message

    async def read_line(self) -> str:
        while "\n" not in self._buffer:
            message = await asyncio.wait_for(self._messages.get(), timeout=TIMEOUT)
            if message["type"] == "http.response.body":
                self._buffer += message.get("body", b"").decode("utf-8")
        line, self._buffer = self._buffer.split("\n", 1)
        return line

    async def read_event(self) -> tuple[str, dict[str, Any]]:
        """Read one SSE frame ("event: X" then "data: {...}"), skipping blank lines."""
        event_type = ""
        while True:
            line = await self.read_line()
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
            elif line.startswith("data: "):
                return event_type, json.loads(line.removeprefix("data: "))

    async def aclose(self) -> None:
        self._disconnect.set()
        if self._task is not None:
            await asyncio.wait_for(self._task, timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_alerts_stream_sends_hello_then_delivers_new_alert(db_engine: AsyncEngine):
    seed_session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with seed_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    seeded_alert_id = None
    sse_client = _RawAsgiSseClient("/api/v1/alerts/stream", query_string=b"poll_seconds=0.25")

    try:
        sse_client.start()

        start = await sse_client.read_start()
        assert start["status"] == 200
        headers = dict(start["headers"])
        assert headers[b"content-type"] == b"text/event-stream; charset=utf-8"

        event_type, payload = await asyncio.wait_for(sse_client.read_event(), timeout=TIMEOUT)
        assert event_type == "hello"
        assert payload == {"status": "connected"}

        # Let the endpoint complete one poll cycle so it establishes its
        # baseline "last seen alert" marker before we insert a new one -
        # otherwise our seeded row could be silently swallowed as the
        # baseline instead of being emitted as an "alert" event.
        await asyncio.sleep(0.4)

        async with seed_session_factory() as seed_session:
            alert = PipelineAlert(
                type="traffic",
                message="SSE end-to-end test alert",
                severity=3,
                confidence=0.9,
                created_at=datetime.now(timezone.utc),
            )
            seed_session.add(alert)
            await seed_session.commit()
            seeded_alert_id = alert.id

        async def _wait_for_our_alert() -> dict[str, Any]:
            while True:
                event_type, payload = await sse_client.read_event()
                if event_type == "alert" and payload.get("id") == str(seeded_alert_id):
                    return payload

        payload = await asyncio.wait_for(_wait_for_our_alert(), timeout=TIMEOUT)
        assert payload["message"] == "SSE end-to-end test alert"
        assert payload["type"] == "traffic"
        assert payload["severity"] == 3
    finally:
        await sse_client.aclose()
        app.dependency_overrides.pop(get_db, None)
        if seeded_alert_id is not None:
            async with seed_session_factory() as cleanup_session:
                obj = await cleanup_session.get(PipelineAlert, seeded_alert_id)
                if obj is not None:
                    await cleanup_session.delete(obj)
                    await cleanup_session.commit()
