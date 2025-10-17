from __future__ import annotations

import asyncio

import pytest

from senderbot.job_manager import JobManager
from senderbot.session_manager import SessionManager
from senderbot.db import Database, SessionRecord


class DummyDB(Database):
    def __init__(self):
        super().__init__("sqlite:///dummy.db")
        self.logged = []
        self.sessions = {
            1: SessionRecord(1, "s1", "+1", "sess1", 1, "active", None, None, 0, None),
            2: SessionRecord(2, "s2", "+2", "sess2", 1, "active", None, None, 0, None),
        }

    async def get_session(self, session_id: int):  # type: ignore[override]
        return self.sessions.get(session_id)

    async def get_sessions(self, status=None):  # type: ignore[override]
        return list(self.sessions.values())

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


class DummySessionManager(SessionManager):
    def __init__(self, db: DummyDB):
        super().__init__(db, api_id=1, api_hash="hash")
        self.db = db
        self.incremented = []

    async def get_client(self, session):  # type: ignore[override]
        class DummyClient:
            async def send_message(self, username, text):
                return 1

            async def send_file(self, username, photo, caption=None):
                return 1

        return DummyClient()

    async def increment_daily(self, session_id: int) -> None:  # type: ignore[override]
        self.incremented.append(session_id)

    async def available_replacement(self, exclude):  # type: ignore[override]
        for session in self.db.sessions.values():
            if session.id not in exclude and session.status == "active":
                return session
        return None


def test_dry_run_split_even_distribution():
    async def _run():
        db = DummyDB()
        manager = DummySessionManager(db)
        job_manager = JobManager(db, manager)
        sessions = [db.sessions[1], db.sessions[2]]
        usernames = [f"user{i}" for i in range(6)]
        allocation = await job_manager.dry_run_split(usernames, sessions)
        assert len(allocation[1]) == 3
        assert len(allocation[2]) == 3

    asyncio.run(_run())


def test_replacement_on_failure(monkeypatch):
    async def _run():
        db = DummyDB()
        manager = DummySessionManager(db)
        job_manager = JobManager(db, manager)

        async def failing_send(session, username, payload):
            from telethon.errors import UserDeactivatedError

            raise UserDeactivatedError(request=None)

        async def ok_send(session, username, payload):
            await DummySessionManager.get_client(manager, session)

        calls = 0

        async def side_effect(session, username, payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                await failing_send(session, username, payload)
            else:
                await ok_send(session, username, payload)

        monkeypatch.setattr(job_manager, "_send_single", side_effect)
        await job_manager._run_job(1, {1: ["user1", "user2"]}, {"text": "hello"})
        assert calls >= 2

    asyncio.run(_run())
