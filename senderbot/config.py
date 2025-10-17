from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    api_id: int
    api_hash: str
    db_url: str
    bot_token: str
    admin_user_id: int
    log_dir: Path = Path("logs")
    consent_prompt: str = (
        "By starting a send job you confirm you have explicit permission to contact "
        "every recipient, comply with Telegram Terms of Service, and respect local laws."
    )

    @property
    def is_sqlite(self) -> bool:
        return self.db_url.startswith("sqlite")

    @staticmethod
    def from_env(prefix: str = "SB_") -> "Settings":
        def _get(name: str, default: Optional[str] = None) -> str:
            env_name = f"{prefix}{name}"
            value = os.getenv(env_name, default)
            if value is None:
                raise RuntimeError(f"Missing required environment variable: {env_name}")
            return value

        api_id = int(_get("API_ID"))
        admin_user_id = int(_get("ADMIN_USER_ID"))
        return Settings(
            api_id=api_id,
            api_hash=_get("API_HASH"),
            db_url=_get("DATABASE_URL"),
            bot_token=_get("BOT_TOKEN"),
            admin_user_id=admin_user_id,
        )


settings = Settings.from_env()
