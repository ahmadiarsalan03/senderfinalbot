from __future__ import annotations

import asyncio

import pytest

from senderbot.job_manager import JobManager
from senderbot.session_manager import SessionManager
from senderbot.db import SessionRecord, Database


class IntegrationDB(Database):
    def __init__(self):
        super().__init__("sqlite:///integration.db")
        self.sessions = {
            i: SessionRecord(i, f"s{i}", f"+{i}", f"sess{i}", 1, "active", None, None, 0, None)
            for i in range(1, 5)
        }
        self.logged = []

    async def get_session(self, session_id: int):  # type: ignore[override]
        return self.sessions.get(session_id)

    async def get_sessions(self, status=None):  # type: ignore[override]
        return [s for s in self.sessions.values() if not status or s.status == status]

    async def has_message(self, session_id, username):  # type: ignore[override]
        return False

    async def log_message(self, session_id, username, message_id):  # type: ignore[override]
        self.logged.append((session_id, username))

    async def upsert_session_daily_count(self, session_id, count, date):  # type: ignore[override]
        session = self.sessions[session_id]
        self.sessions[session_id] = SessionRecord(
            session.id,
            session.label,
            session.phone,
            session.string_session,
            session.agent_id,
            session.status,
            session.created_at,
            session.last_active,
            count,
            date,
        )

    async def mark_session_status(self, session_id, status):  # type: ignore[override]
        session = self.sessions[session_id]
        self.sessions[session_id] = SessionRecord(
            session.id,
            session.label,
            session.phone,
            session.string_session,
            session.agent_id,
            status,
            session.created_at,
            session.last_active,
            session.daily_sent_count,
            session.daily_sent_date,
        )


class IntegrationSessionManager(SessionManager):
    def __init__(self, db: IntegrationDB):
        super().__init__(db, api_id=1, api_hash="hash")
        self.db = db

    async def get_client(self, session):  # type: ignore[override]
        class Dummy:
            async def send_message(self, username, text):
                return 1

        return Dummy()

    async def increment_daily(self, session_id: int) -> None:  # type: ignore[override]
        pass

    async def available_replacement(self, exclude):  # type: ignore[override]
        for session in self.db.sessions.values():
            if session.id not in exclude and session.status == "active":
                return session
        return None


def test_integration_replacement_flow(monkeypatch):
    async def _run():
        db = IntegrationDB()
        manager = IntegrationSessionManager(db)
        job_manager = JobManager(db, manager)

        usernames = [f"user{i}" for i in range(40)]
        allocation = await job_manager.dry_run_split(usernames, list(db.sessions.values()))

        calls = {}

        async def side_effect(session, username, payload):
            calls.setdefault(session.id, 0)
            calls[session.id] += 1
            if session.id == 1 and calls[session.id] == 1:
                from telethon.errors import AuthKeyError

                raise AuthKeyError(request=None)
            await manager.db.log_message(session.id, username, 1)

        monkeypatch.setattr(job_manager, "_send_single", side_effect)
        await job_manager._run_job(1, allocation, {"text": "hello"})
        processed = {username for _, username in db.logged}
        assert processed == set(usernames)
        assert calls[1] == 1

    asyncio.run(_run())
