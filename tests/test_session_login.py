from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from senderbot.session_manager import SessionManager
from senderbot.agents import AgentPool, Agent
from senderbot.db import Database


class MemoryDB(Database):
    def __init__(self) -> None:
        super().__init__("sqlite:///memory.db")
        self.inserted = []

    async def create_session(self, label, phone, string_session, agent_id, status):  # type: ignore[override]
        self.inserted.append(
            {
                "label": label,
                "phone": phone,
                "string_session": string_session,
                "agent_id": agent_id,
                "status": status,
            }
        )
        return len(self.inserted)


def make_agent_pool() -> AgentPool:
    agent = Agent(
        id=1,
        device_model="iPhone",
        platform="iOS",
        app_version="9.4.2",
        system_version="iOS 17",
        lang_code="en",
        tz="UTC",
        cpu_arch="arm64",
        user_agent="ua",
        device_id="abc",
    )
    return AgentPool([agent])


class StubSession:
    def save(self) -> str:
        return "SESSION"


class StubClient:
    def __init__(self, needs_password: bool = False):
        self.needs_password = needs_password
        self.session = StubSession()
        self.password_used: str | None = None
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def sign_in(self, **kwargs):
        if "password" in kwargs:
            self.password_used = kwargs["password"]
            return
        if self.needs_password:
            from telethon.errors import SessionPasswordNeededError

            raise SessionPasswordNeededError(request=None)


def test_login_with_password(monkeypatch):
    async def _run():
        db = MemoryDB()
        manager = SessionManager(db, api_id=123, api_hash="hash", agent_pool=make_agent_pool())

        stub_client = StubClient(needs_password=True)

        monkeypatch.setattr("senderbot.session_manager.TelegramClient", lambda *a, **k: stub_client)

        async def send_code(client, phone):
            return True

        codes = asyncio.Queue()
        await codes.put("12345")

        async def get_code():
            return await codes.get()

        async def get_password():
            return "password123"

        result = await manager.login("+15551234567", send_code, get_code, get_password)
        assert result.success is True
        assert stub_client.password_used == "password123"
        assert db.inserted

    asyncio.run(_run())
