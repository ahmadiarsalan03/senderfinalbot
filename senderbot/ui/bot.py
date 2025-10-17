from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from telethon import Button, TelegramClient, events
from telethon.tl.custom import Button as InlineButton

from ..config import settings
from ..session_manager import SessionManager
from ..job_manager import JobManager
from ..db import Database, SessionRecord

logger = logging.getLogger(__name__)

MAIN_MENU = "main_menu"
CONSENT_CONFIRMED = "consent_confirmed"


@dataclass(slots=True)
class UserState:
    step: str = MAIN_MENU
    payload: Dict[str, str] | None = None


class SenderBot:
    def __init__(self, db: Database, session_manager: SessionManager, job_manager: JobManager) -> None:
        self.db = db
        self.session_manager = session_manager
        self.job_manager = job_manager
        self.client = TelegramClient(
            "bot",
            api_id=session_manager.api_id,
            api_hash=session_manager.api_hash,
        ).start(bot_token=settings.bot_token)
        self.states: Dict[int, UserState] = {}

    def _state(self, user_id: int) -> UserState:
        return self.states.setdefault(user_id, UserState())

    async def start(self) -> None:
        self.client.add_event_handler(self._on_start, events.NewMessage(pattern="/start"))
        self.client.add_event_handler(self._on_callback, events.CallbackQuery())
        await self.client.run_until_disconnected()

    def main_keyboard(self) -> List[List[InlineButton]]:
        return [
            [Button.inline("Add account", b"add_account")],
            [Button.inline("Extract IDs", b"extract_ids")],
            [Button.inline("Account status", b"account_status")],
            [Button.inline("Send messages", b"send_messages")],
        ]

    async def _on_start(self, event) -> None:
        await event.respond("Sender Bot ready.", buttons=self.main_keyboard())

    async def _on_callback(self, event) -> None:
        user_id = event.sender_id
        if user_id != settings.admin_user_id:
            await event.answer("Unauthorized", alert=True)
            return
        data = event.data.decode()
        logger.debug("Callback %s from %s", data, user_id)
        if data == "back":
            self.states.pop(user_id, None)
            await event.edit("Main menu", buttons=self.main_keyboard())
            return
        state = self._state(user_id)
        if data == "add_account":
            state.step = "add_account_phone"
            await event.edit("Enter phone number (international format):", buttons=[[Button.inline("Back", b"back")]])
        elif data == "extract_ids":
            state.step = "extract_group"
            await event.edit("Send group link or name:", buttons=[[Button.inline("Back", b"back")]])
        elif data == "account_status":
            await self._show_account_status(event)
        elif data == "send_messages":
            state.step = CONSENT_CONFIRMED
            await event.edit(
                settings.consent_prompt + "\nPress continue to proceed.",
                buttons=[
                    [Button.inline("I Agree", b"send_content")],
                    [Button.inline("Back", b"back")],
                ],
            )
        elif data == "send_content":
            state.step = "send_content"
            state.payload = {}
            await event.edit("Send text message or upload media.", buttons=[[Button.inline("Back", b"back")]])
        elif data.startswith("session_select:"):
            session_id = int(data.split(":", 1)[1])
            payload = state.payload or {}
            selected = json.loads(payload.get("sessions", "[]")) if payload.get("sessions") else []
            if session_id in selected:
                selected.remove(session_id)
            else:
                selected.append(session_id)
            payload["sessions"] = json.dumps(selected)
            state.payload = payload
            await event.answer(f"Selected sessions: {selected}")
        elif data == "confirm_send":
            await self._start_sending(event, state)
        elif data == "login_status":
            await self._show_login_status(event)
        elif data == "report_status":
            await self._show_report_status(event)

    async def _show_account_status(self, event) -> None:
        buttons = [
            [Button.inline("Login status", b"login_status")],
            [Button.inline("Report status", b"report_status")],
            [Button.inline("Back", b"back")],
        ]
        await event.edit("Choose status view:", buttons=buttons)

    async def _show_login_status(self, event) -> None:
        sessions = await self.db.get_sessions()
        lines = [
            f"{s.id}: {s.label} — {s.status} — agent {s.agent_id} — daily {s.daily_sent_count}"
            for s in sessions
        ]
        message = "\n".join(lines) or "No sessions saved."
        await event.edit(message, buttons=[[Button.inline("Back", b"back")]])

    async def _show_report_status(self, event) -> None:
        sessions = await self.db.get_sessions(status="active")
        lines: List[str] = []
        for session in sessions:
            status_text = await self._check_spam_bot(session)
            lines.append(f"{session.label}: {status_text}")
        await event.edit("\n".join(lines) or "No sessions saved.", buttons=[[Button.inline("Back", b"back")]])

    async def _check_spam_bot(self, session: SessionRecord) -> str:
        client = await self.session_manager.get_client(session)
        lock = await self.session_manager.acquire(session.id)
        async with lock:
            await client.send_message("@spambot", "/start")
            async for msg in client.iter_messages("@spambot", limit=1):
                if msg.message.strip() == (
                    "Good news, no limits are currently applied to your account. You’re free as a bird!"
                ):
                    return "OK"
                return "REPORTED"
        return "UNKNOWN"

    async def _start_sending(self, event, state: UserState) -> None:
        payload = state.payload or {}
        text = payload.get("text")
        photo = payload.get("photo")
        caption = payload.get("caption")
        sessions_json = payload.get("sessions")
        usernames_raw = payload.get("usernames") or ""
        sessions_ids = json.loads(sessions_json) if sessions_json else []
        usernames = [u.strip() for u in usernames_raw.splitlines() if u.strip()]
        sessions = await self.session_manager.eligible_sessions(sessions_ids)
        if not sessions:
            await event.edit("No sessions available for sending.", buttons=[[Button.inline("Back", b"back")]])
            return
        job_id = await self.job_manager.create_job(
            job_type="send",
            usernames=usernames,
            created_by=event.sender_id,
            params={"text": text, "photo": photo, "caption": caption, "sessions": sessions_ids},
        )
        await self.job_manager.send_messages(job_id, usernames, sessions, {"text": text, "photo": photo, "caption": caption})
        await event.edit(f"Job {job_id} started with {len(usernames)} usernames.", buttons=[[Button.inline("Back", b"back")]])

    async def handle_incoming_message(self, event) -> None:
        user_id = event.sender_id
        if user_id != settings.admin_user_id:
            await event.respond("Unauthorized")
            return
        state = self._state(user_id)
        if state.step == "add_account_phone":
            phone = event.raw_text.strip()
            state.payload = {"phone": phone}
            await event.respond("Waiting for OTP code...", buttons=[[Button.inline("Back", b"back")]])
            # Actual login handled asynchronously by CLI/worker.
        elif state.step == "extract_group":
            payload = state.payload or {}
            payload["group"] = event.raw_text.strip()
            state.payload = payload
            state.step = "extract_count"
            await event.respond("How many usernames to extract?", buttons=[[Button.inline("Back", b"back")]])
        elif state.step == "extract_count":
            payload = state.payload or {}
            payload["count"] = event.raw_text.strip()
            state.payload = payload
            await self._prompt_session_selection(event, state)
        elif state.step == "send_content":
            payload = state.payload or {}
            if event.photo:
                path = Path(f"uploads/{event.id}.jpg")
                path.parent.mkdir(exist_ok=True)
                await event.download_media(path)
                payload["photo"] = str(path)
                payload["caption"] = event.raw_text or ""
            else:
                payload["text"] = event.raw_text
            state.payload = payload
            await event.respond("Send usernames list (text or upload .txt).", buttons=[[Button.inline("Back", b"back")]])
            state.step = "send_usernames"
        elif state.step == "send_usernames":
            payload = state.payload or {}
            if event.document:
                path = Path(f"uploads/{event.id}.txt")
                path.parent.mkdir(exist_ok=True)
                await event.download_media(path)
                payload["usernames"] = path.read_text(encoding="utf-8")
            else:
                payload["usernames"] = event.raw_text
            state.payload = payload
            await self._prompt_session_selection(event, state, confirm=True)

    async def _prompt_session_selection(self, event, state: UserState, confirm: bool = False) -> None:
        sessions = await self.session_manager.eligible_sessions()
        buttons: List[List[InlineButton]] = []
        for session in sessions:
            buttons.append([Button.inline(f"{session.label}", f"session_select:{session.id}".encode())])
        if confirm:
            buttons.append([Button.inline("Start sending", b"confirm_send")])
        buttons.append([Button.inline("Back", b"back")])
        await event.respond("Select sessions to use:", buttons=buttons)


async def run_bot(db: Database, session_manager: SessionManager, job_manager: JobManager) -> None:
    bot = SenderBot(db, session_manager, job_manager)
    bot.client.add_event_handler(bot.handle_incoming_message, events.NewMessage())
    await bot.start()
