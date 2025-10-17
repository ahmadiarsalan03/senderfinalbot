from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Callable, Awaitable

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from .agents import AgentPool, default_agent_pool
from .db import Database, SessionRecord

logger = logging.getLogger(__name__)

SendCodeFunc = Callable[[TelegramClient, str], Awaitable[bool]]
GetValueFunc = Callable[[], Awaitable[str]]


@dataclass(slots=True)
class SessionLoginResult:
    success: bool
    error: Optional[str]
    session_id: Optional[int] = None


class SessionManager:
    DAILY_LIMIT = 25

    def __init__(self, db: Database, api_id: int, api_hash: str, agent_pool: AgentPool = default_agent_pool) -> None:
        self.db = db
        self.api_id = api_id
        self.api_hash = api_hash
        self.agent_pool = agent_pool
        self._clients: Dict[int, TelegramClient] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    async def ensure_daily_reset(self, session: SessionRecord) -> None:
        now = datetime.now(timezone.utc)
        if session.daily_sent_date is None or session.daily_sent_date.date() != now.date():
            logger.debug("Resetting daily count for session %s", session.id)
            await self.db.upsert_session_daily_count(session.id, 0, now)

    async def get_client(self, session: SessionRecord) -> TelegramClient:
        if session.id not in self._clients:
            agent = self.agent_pool.get(session.agent_id)
            client = TelegramClient(
                StringSession(session.string_session),
                api_id=self.api_id,
                api_hash=self.api_hash,
                device_model=agent.device_model,
                system_version=agent.system_version,
                app_version=agent.app_version,
                system_lang_code=agent.lang_code,
                lang_code=agent.lang_code,
            )
            await client.connect()
            self._clients[session.id] = client
            self._locks[session.id] = asyncio.Lock()
        return self._clients[session.id]

    async def acquire(self, session_id: int) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def login(
        self,
        phone: str,
        send_code_func: SendCodeFunc,
        get_code_func: GetValueFunc,
        get_password_func: GetValueFunc,
    ) -> SessionLoginResult:
        agent = self.agent_pool.random()
        client = TelegramClient(
            StringSession(),
            api_id=self.api_id,
            api_hash=self.api_hash,
            device_model=agent.device_model,
            system_version=agent.system_version,
            app_version=agent.app_version,
            system_lang_code=agent.lang_code,
            lang_code=agent.lang_code,
        )
        try:
            await client.connect()
            sent = await send_code_func(client, phone)
            if not sent:
                return SessionLoginResult(success=False, error="Failed to send code")
            code = await get_code_func()
            try:
                await client.sign_in(phone=phone, code=code)
            except SessionPasswordNeededError:
                password = await get_password_func()
                await client.sign_in(password=password)
            string_session = client.session.save()
            session_id = await self.db.create_session(
                label=phone,
                phone=phone,
                string_session=string_session,
                agent_id=agent.id,
                status="active",
            )
            return SessionLoginResult(success=True, error=None, session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Login failed")
            return SessionLoginResult(success=False, error=str(exc))
        finally:
            await client.disconnect()

    async def increment_daily(self, session_id: int) -> None:
        session = await self.db.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        await self.ensure_daily_reset(session)
        new_count = session.daily_sent_count + 1
        await self.db.upsert_session_daily_count(session_id, new_count, datetime.now(timezone.utc))

    async def eligible_sessions(self, session_ids: Optional[Iterable[int]] = None) -> List[SessionRecord]:
        sessions = await self.db.get_sessions(status="active")
        if session_ids:
            session_ids_set = set(session_ids)
            sessions = [s for s in sessions if s.id in session_ids_set]
        result: List[SessionRecord] = []
        for session in sessions:
            await self.ensure_daily_reset(session)
            if session.daily_sent_count < self.DAILY_LIMIT:
                result.append(session)
        return result

    async def mark_blocked(self, session_id: int, reason: str) -> None:
        logger.warning("Marking session %s as blocked: %s", session_id, reason)
        await self.db.mark_session_status(session_id, "blocked")

    async def available_replacement(self, exclude: Iterable[int]) -> Optional[SessionRecord]:
        sessions = await self.eligible_sessions()
        excluded = set(exclude)
        for session in sessions:
            if session.id not in excluded:
                return session
        return None

    async def close(self) -> None:
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()
        self._locks.clear()
