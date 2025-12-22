"""
Integration tests for the session endpoints.

These tests spin up the FastAPI application using the in‑memory SQLite
database and verify that sessions can be created, messages can be
exchanged and memory review operates as expected. The tests use
pytest‑asyncio to run asynchronous test functions.
"""
import asyncio
import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from negot.api.main import create_app
from negot.core.config import get_settings
from negot.core.db import init_db_schema, get_db_session


@pytest.fixture(autouse=True)
def set_test_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the DATABASE_URL to use an in-memory SQLite DB for tests."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("NEGOT_ENV", "test")
    monkeypatch.setenv("LITELLM_MODEL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    # Recreate settings cache so new env takes effect
    get_settings.cache_clear()


@pytest.fixture()
async def app() -> FastAPI:
    """Create and initialise the FastAPI app for testing."""
    application = create_app()
    # Initialise DB schema
    await init_db_schema()
    return application


@pytest.mark.asyncio
async def test_create_session_and_message_flow(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a session with a salary negotiation topic
        res = await client.post("/sessions", json={"topic_text": "I want to negotiate my salary"}, headers={"X-User-Id": "1"})
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        session_id = data["session_id"]
        # Post a message
        res2 = await client.post(f"/sessions/{session_id}/messages", json={"content": "I'd like to discuss my compensation."}, headers={"X-User-Id": "1"})
        assert res2.status_code == 200
        msg_data = res2.json()
        assert msg_data.get("counterparty_message") is not None
        # End the session
        res3 = await client.post(f"/sessions/{session_id}/end", headers={"X-User-Id": "1"})
        assert res3.status_code == 200
        recap = res3.json()
        assert "recap" in recap


@pytest.mark.asyncio
async def test_memory_review(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"topic_text": "test"}, headers={"X-User-Id": "2"})
        session_id = res.json()["session_id"]
        # Post a message that yields no facts
        await client.post(f"/sessions/{session_id}/messages", json={"content": "Hello"}, headers={"X-User-Id": "2"})
        # End session
        await client.post(f"/sessions/{session_id}/end", headers={"X-User-Id": "2"})
        # Memory review with no facts
        res2 = await client.post(
            f"/sessions/{session_id}/memory-review",
            json={"decisions": []},
            headers={"X-User-Id": "2"},
        )
        assert res2.status_code == 200
        assert res2.json()["updated_facts"] == []
