from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings, settings
from .db import Database
from .session_manager import SessionManager
from .job_manager import JobManager
from .agents import default_agent_pool
from .ui.bot import run_bot

logging.basicConfig(level=logging.INFO)

app = typer.Typer(help="Telegram sender bot CLI")
console = Console()


def _build_runtime(settings: Settings) -> tuple[Database, SessionManager, JobManager]:
    db = Database(settings.db_url)
    session_manager = SessionManager(db, api_id=settings.api_id, api_hash=settings.api_hash, agent_pool=default_agent_pool)
    job_manager = JobManager(db, session_manager)
    return db, session_manager, job_manager


@app.command()
def init_db(schema: Path = typer.Option(Path("schema.sql"), exists=True, file_okay=True, readable=True)) -> None:
    """Initialize the database using schema.sql."""
    content = schema.read_text(encoding="utf-8")
    db = Database(settings.db_url)
    async def _run() -> None:
        await db.connect()
        for statement in filter(None, (stmt.strip() for stmt in content.split(";"))):
            await db.execute(statement)
        await db.disconnect()
    asyncio.run(_run())
    console.print("Database initialized")


@app.command()
def run() -> None:
    """Run the Telegram bot."""
    async def _run() -> None:
        db, session_manager, job_manager = _build_runtime(settings)
        await db.connect()
        try:
            await run_bot(db, session_manager, job_manager)
        finally:
            await session_manager.close()
            await db.disconnect()
    asyncio.run(_run())


@app.command()
def dry_run(usernames_file: Path, session_ids: Optional[str] = typer.Option(None, help="Comma separated session IDs")) -> None:
    """Preview username allocation across sessions."""
    usernames = [line.strip() for line in usernames_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    async def _run() -> None:
        db, session_manager, job_manager = _build_runtime(settings)
        await db.connect()
        try:
            sessions = await session_manager.eligible_sessions(
                [int(s) for s in session_ids.split(",") if s]
                if session_ids
                else None
            )
            allocation = await job_manager.dry_run_split(usernames, sessions)
            table = Table(title="Dry-run allocation")
            table.add_column("Session ID")
            table.add_column("Usernames")
            for session_id, names in allocation.items():
                table.add_row(str(session_id), ", ".join(names))
            console.print(table)
        finally:
            await session_manager.close()
            await db.disconnect()
    asyncio.run(_run())


if __name__ == "__main__":
    app()
