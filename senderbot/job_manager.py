from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from telethon.errors import FloodWaitError, UserDeactivatedError, AuthKeyError

from .db import Database, JobRecord, SessionRecord
from .session_manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SendResult:
    username: str
    status: str
    session_id: Optional[int]
    error: Optional[str] = None


class JobManager:
    def __init__(self, db: Database, session_manager: SessionManager) -> None:
        self.db = db
        self.session_manager = session_manager
        self._active_jobs: Dict[int, asyncio.Task] = {}

    @property
    def active_jobs(self) -> Dict[int, asyncio.Task]:
        return self._active_jobs

    async def create_job(self, job_type: str, usernames: Sequence[str], created_by: int, params: Dict) -> int:
        job = JobRecord(
            id=0,
            type=job_type,
            params=dict(params),
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            status="pending",
        )
        job_id = await self.db.insert_job(job)
        await self.db.insert_job_items(job_id, list(usernames))
        return job_id

    async def dry_run_split(self, usernames: Sequence[str], sessions: Sequence[SessionRecord]) -> Dict[int, List[str]]:
        allocation: Dict[int, List[str]] = {s.id: [] for s in sessions}
        if not sessions:
            return allocation
        for index, username in enumerate(usernames):
            session = sessions[index % len(sessions)]
            allocation[session.id].append(username)
        return allocation

    async def send_messages(
        self,
        job_id: int,
        usernames: Sequence[str],
        sessions: Sequence[SessionRecord],
        message_payload: Dict[str, Optional[str]],
    ) -> None:
        allocation = await self.dry_run_split(usernames, sessions)
        job_task = asyncio.create_task(
            self._run_job(job_id, allocation, message_payload),
            name=f"job-{job_id}",
        )
        self._active_jobs[job_id] = job_task
        job_task.add_done_callback(lambda _: self._active_jobs.pop(job_id, None))

    async def _run_job(self, job_id: int, allocation: Dict[int, List[str]], payload: Dict[str, Optional[str]]) -> None:
        results: List[SendResult] = []
        replaced_sessions: List[Tuple[int, int]] = []
        pending = [
            self._process_session(job_id, session_id, usernames, payload, results, replaced_sessions)
            for session_id, usernames in allocation.items()
        ]
        await asyncio.gather(*pending)
        success = sum(1 for r in results if r.status == "sent")
        failed = [r for r in results if r.status == "failed"]
        logger.info(
            "Job %s finished: %s total, %s success, %s failed, replacements=%s",
            job_id,
            len(results),
            success,
            len(failed),
            replaced_sessions,
        )

    async def _process_session(
        self,
        job_id: int,
        session_id: int,
        usernames: Sequence[str],
        payload: Dict[str, Optional[str]],
        results: List[SendResult],
        replacements: List[Tuple[int, int]],
    ) -> None:
        session = await self.session_manager.db.get_session(session_id)
        if not session or session.status != "active":
            logger.warning("Session %s unavailable for job %s", session_id, job_id)
            return
        lock = await self.session_manager.acquire(session_id)
        async with lock:
            index = 0
            total = len(usernames)
            while index < total:
                username = usernames[index]
                if await self.session_manager.db.has_message(session_id, username):
                    results.append(SendResult(username=username, status="skipped", session_id=session_id))
                    index += 1
                    continue
                try:
                    await self._send_single(session, username, payload)
                    await self.session_manager.increment_daily(session.id)
                    results.append(SendResult(username=username, status="sent", session_id=session_id))
                except FloodWaitError as exc:  # type: ignore[misc]
                    await self.session_manager.mark_blocked(session.id, f"Flood wait {exc.seconds}")
                    replacement = await self.session_manager.available_replacement({session.id})
                    if replacement:
                        replacements.append((session.id, replacement.id))
                        await self._process_session(job_id, replacement.id, usernames[index:], payload, results, replacements)
                        break
                    else:
                        results.append(SendResult(username=username, status="failed", session_id=session_id, error="FloodWait"))
                except (UserDeactivatedError, AuthKeyError) as exc:
                    await self.session_manager.mark_blocked(session.id, str(exc))
                    replacement = await self.session_manager.available_replacement({session.id})
                    if replacement:
                        replacements.append((session.id, replacement.id))
                        await self._process_session(job_id, replacement.id, usernames[index:], payload, results, replacements)
                        break
                    else:
                        results.append(SendResult(username=username, status="failed", session_id=session_id, error=str(exc)))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to send to %s using session %s", username, session.id)
                    results.append(SendResult(username=username, status="failed", session_id=session_id, error=str(exc)))
                index += 1

    async def _send_single(self, session: SessionRecord, username: str, payload: Dict[str, Optional[str]]) -> None:
        client = await self.session_manager.get_client(session)
        if payload.get("photo"):
            await client.send_file(username, payload["photo"], caption=payload.get("caption"))
        else:
            await client.send_message(username, payload.get("text"))
        message_id = int(datetime.now().timestamp())
        await self.db.log_message(session.id, username, message_id)
