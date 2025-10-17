# Sender Bot

Async Telegram sender bot built with Telethon, asyncio, and SQL persistence. The project exposes both a Telegram bot UI and a CLI for orchestration. Sessions are stored using Telethon `StringSession` tokens and augmented with a large pool of pseudo-random device fingerprints (agents) to reduce detection risk.

> **Legal warning**: Automated scraping and unsolicited messaging can violate Telegram Terms of Service and applicable laws. Only operate this project if you have explicit permission from message recipients. The in-bot flow requires an explicit confirmation of compliance before any send job starts.

## Features

* Telegram bot UI with inline keyboard navigation and Back buttons on every multi-step flow.
* Add account flow that logs in user sessions using randomized agent profiles (100+ bundled).
* Group username extraction with session selection and `.txt` export.
* Session health tools: login status summary and automated @spambot checks.
* High-performance send engine with per-session daily limits, concurrency, dynamic replacement, retries, and per-target idempotency.
* Async database support for SQLite (default) and PostgreSQL.
* CLI utilities for database initialization, bot runtime, and dry-run planning.
* Structured logging with support for rotating files (configure via `logging.conf`).
* Comprehensive unit tests (pytest + pytest-asyncio) including integration simulation of session replacement.

## Project layout

```
senderfinalbot/
├── agents/
│   └── agents.json
├── scripts/
│   └── generate_agents.py
├── senderbot/
│   ├── __init__.py
│   ├── agents.py
│   ├── cli.py
│   ├── config.py
│   ├── db.py
│   ├── job_manager.py
│   ├── session_manager.py
│   └── ui/
│       ├── __init__.py
│       └── bot.py
├── tests/
│   ├── __init__.py
│   ├── test_integration.py
│   ├── test_job_manager.py
│   ├── test_session_login.py
│   └── test_username_extraction.py
├── schema.sql
├── README.md
└── pyproject.toml
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[development]
```

Create a `.env` file in the project root with the following variables:

```
SB_API_ID=123456
SB_API_HASH=your_api_hash
SB_BOT_TOKEN=1234:bot_token
SB_DATABASE_URL=sqlite:///senderbot.db
SB_ADMIN_USER_ID=123456789
```

For PostgreSQL use `postgresql://user:password@host:port/database`.

Initialize the database:

```bash
senderbot init-db
```

Populate the agents table (optional but recommended for analytics):

```bash
sqlite3 senderbot.db ".mode json" "INSERT INTO agents (id, json_profile) SELECT json_extract(value, '$.id'), value FROM json_each(readfile('agents/agents.json'))"
```

## Running the bot

```bash
senderbot run
```

The bot listens as the account associated with `SB_BOT_TOKEN`. Interact with it from the admin account (`SB_ADMIN_USER_ID`).

## CLI dry-run mode

```bash
senderbot dry-run usernames.txt --session-ids 1,2,3
```

This prints a table showing how usernames will be distributed among sessions.

## Testing

```bash
pytest
```

## Database schema

The schema is defined in [`schema.sql`](schema.sql) and includes tables for agents, sessions, jobs, job items, and message logs with idempotency constraints.

## Agents

`agents/agents.json` contains 100 deterministically generated agent profiles. Regenerate with:

```bash
python scripts/generate_agents.py
```

## Unit tests overview

* `test_session_login.py` – verifies login flow handles OTP and 2FA using mocked Telethon client responses.
* `test_username_extraction.py` – ensures message parsing collects unique usernames and skips duplicates.
* `test_job_manager.py` – validates username splitting, replacement logic, and per-session limits.
* `test_integration.py` – simulates four sessions sending to 40 usernames, forces a failure, and asserts replacement/resume behavior.

## Prompt for Codex

```
Create a production-ready async Python project named "Sender Bot". Use Telethon for Telegram interactions, asyncio for concurrency, and SQLite/PostgreSQL for persistence. Implement session management with randomized device agents, username extraction, message sending with rate limits and automatic replacement, CLI tools, unit tests, and documentation. Include a legal consent step before sending and provide at least 100 agent fingerprints in JSON plus a generator script.
```

