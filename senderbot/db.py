from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional

import asyncpg
import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised for database-level errors."""


@dataclass(slots=True)
class SessionRecord:
    id: int
    label: str
    phone: str
    string_session: str
    agent_id: int
    status: str
    created_at: datetime
    last_active: Optional[datetime]
    daily_sent_count: int
    daily_sent_date: Optional[datetime]


@dataclass(slots=True)
class AgentRecord:
    id: int
    profile: Dict[str, Any]


@dataclass(slots=True)
class JobRecord:
    id: int
    type: str
    params: Dict[str, Any]
    created_by: int
    created_at: datetime
    status: str


@dataclass(slots=True)
class JobItemRecord:
    id: int
    job_id: int
    username: str
    assigned_session_id: Optional[int]
    status: str
    error_message: Optional[str]


class Database:
    """Simple wrapper supporting asyncpg and aiosqlite backends."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Any = None
        self._is_sqlite = dsn.startswith("sqlite")

    async def connect(self) -> None:
        if self._is_sqlite:
            self._pool = await aiosqlite.connect(self.dsn.split("///", 1)[1])
            self._pool.row_factory = aiosqlite.Row
        else:
            self._pool = await asyncpg.create_pool(self.dsn)
        logger.debug("Database connected using %s", "sqlite" if self._is_sqlite else "postgres")

    async def disconnect(self) -> None:
        if self._pool:
            if self._is_sqlite:
                await self._pool.close()
            else:
                await self._pool.close()
            self._pool = None

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        if self._is_sqlite:
            async with self._pool.execute("BEGIN"):
                try:
                    yield self._pool
                    await self._pool.commit()
                except Exception:
                    await self._pool.rollback()
                    raise
        else:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    yield conn

    async def execute(self, query: str, *args: Any) -> None:
        if self._is_sqlite:
            await self._pool.execute(query, args)
            await self._pool.commit()
        else:
            async with self._pool.acquire() as conn:
                await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        if self._is_sqlite:
            async with self._pool.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        else:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(row) for row in rows]

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        if self._is_sqlite:
            async with self._pool.execute(query, args) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        else:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row else None

    async def executemany(self, query: str, args_iter: Iterable[Iterable[Any]]) -> None:
        if self._is_sqlite:
            await self._pool.executemany(query, args_iter)
            await self._pool.commit()
        else:
            async with self._pool.acquire() as conn:
                await conn.executemany(query, args_iter)

    # Specific helpers
    async def get_sessions(self, status: Optional[str] = None) -> List[SessionRecord]:
        query = "SELECT * FROM sessions"
        params: List[Any] = []
        if status:
            query += " WHERE status = $1" if not self._is_sqlite else " WHERE status = ?"
            params.append(status)
        rows = await self.fetch(query, *params)
        return [self._row_to_session(r) for r in rows]

    async def get_session(self, session_id: int) -> Optional[SessionRecord]:
        query = "SELECT * FROM sessions WHERE id = $1" if not self._is_sqlite else "SELECT * FROM sessions WHERE id = ?"
        row = await self.fetchrow(query, session_id)
        return self._row_to_session(row) if row else None

    async def upsert_session_daily_count(self, session_id: int, count: int, date: datetime) -> None:
        query = (
            "UPDATE sessions SET daily_sent_count = $1, daily_sent_date = $2 WHERE id = $3"
            if not self._is_sqlite
            else "UPDATE sessions SET daily_sent_count = ?, daily_sent_date = ? WHERE id = ?"
        )
        await self.execute(query, count, date, session_id)

    async def mark_session_status(self, session_id: int, status: str) -> None:
        query = "UPDATE sessions SET status = $1 WHERE id = $2" if not self._is_sqlite else "UPDATE sessions SET status = ? WHERE id = ?"
        await self.execute(query, status, session_id)

    async def create_session(
        self,
        label: str,
        phone: str,
        string_session: str,
        agent_id: int,
        status: str,
    ) -> int:
        now = datetime.now(timezone.utc)
        if self._is_sqlite:
            query = (
                "INSERT INTO sessions (label, phone, string_session, agent_id, status, created_at, daily_sent_count, daily_sent_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
            await self.execute(query, label, phone, string_session, agent_id, status, now, 0, now)
            row = await self.fetchrow("SELECT last_insert_rowid() AS id")
            return int(row["id"]) if row else 0
        query = (
            "INSERT INTO sessions (label, phone, string_session, agent_id, status, created_at, daily_sent_count, daily_sent_date) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, label, phone, string_session, agent_id, status, now, 0, now)
            return int(row["id"])

    async def insert_job(self, job: JobRecord) -> int:
        query = (
            "INSERT INTO jobs (type, params, created_by, created_at, status) VALUES ($1, $2, $3, $4, $5) RETURNING id"
            if not self._is_sqlite
            else "INSERT INTO jobs (type, params, created_by, created_at, status) VALUES (?, ?, ?, ?, ?)"
        )
        params = (job.type, json.dumps(job.params), job.created_by, job.created_at, job.status)
        if self._is_sqlite:
            await self.execute(query, *params)
            row = await self.fetchrow("SELECT last_insert_rowid() AS id")
            return int(row["id"]) if row else 0
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            return int(row["id"])  # type: ignore[index]

    async def insert_job_items(self, job_id: int, usernames: List[str]) -> None:
        query = (
            "INSERT INTO job_items (job_id, username, status) VALUES ($1, $2, $3)"
            if not self._is_sqlite
            else "INSERT INTO job_items (job_id, username, status) VALUES (?, ?, ?)"
        )
        await self.executemany(query, ((job_id, username, "pending") for username in usernames))

    async def update_job_item(self, item_id: int, status: str, session_id: Optional[int], error: Optional[str]) -> None:
        query = (
            "UPDATE job_items SET status = $1, assigned_session_id = $2, error_message = $3 WHERE id = $4"
            if not self._is_sqlite
            else "UPDATE job_items SET status = ?, assigned_session_id = ?, error_message = ? WHERE id = ?"
        )
        await self.execute(query, status, session_id, error, item_id)

    async def log_message(self, session_id: int, username: str, message_id: int) -> None:
        query = (
            "INSERT INTO message_log (session_id, username, message_id, timestamp) VALUES ($1, $2, $3, $4)"
            if not self._is_sqlite
            else "INSERT INTO message_log (session_id, username, message_id, timestamp) VALUES (?, ?, ?, ?)"
        )
        await self.execute(query, session_id, username, message_id, datetime.now(timezone.utc))

    async def has_message(self, session_id: int, username: str) -> bool:
        query = (
            "SELECT 1 FROM message_log WHERE session_id = $1 AND username = $2"
            if not self._is_sqlite
            else "SELECT 1 FROM message_log WHERE session_id = ? AND username = ?"
        )
        row = await self.fetchrow(query, session_id, username)
        return row is not None

    @staticmethod
    def _row_to_session(row: Dict[str, Any]) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            label=row["label"],
            phone=row["phone"],
            string_session=row["string_session"],
            agent_id=row["agent_id"],
            status=row["status"],
            created_at=_as_datetime(row["created_at"]),
            last_active=_as_datetime(row.get("last_active")) if row.get("last_active") else None,
            daily_sent_count=row.get("daily_sent_count", 0),
            daily_sent_date=_as_datetime(row.get("daily_sent_date")) if row.get("daily_sent_date") else None,
        )


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Cannot convert {value!r} to datetime")
