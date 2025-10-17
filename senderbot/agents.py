from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from random import choice
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Agent:
    id: int
    device_model: str
    platform: str
    app_version: str
    system_version: str
    lang_code: str
    tz: str
    cpu_arch: str
    user_agent: str
    device_id: str

    def to_telethon_kwargs(self) -> Dict[str, str]:
        return {
            "device_model": self.device_model,
            "app_version": self.app_version,
            "system_version": self.system_version,
            "system_lang_code": self.lang_code,
            "lang_code": self.lang_code,
        }


class AgentPool:
    def __init__(self, agents: List[Agent]) -> None:
        self._agents = agents
        if len(self._agents) < 1:
            raise ValueError("Agent pool must contain at least one agent")

    @classmethod
    def from_json(cls, path: Path) -> "AgentPool":
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        agents = [Agent(id=i, **entry) for i, entry in enumerate(payload, start=1)]
        logger.debug("Loaded %d agents", len(agents))
        if len(agents) < 100:
            logger.warning("Agent pool smaller than expected minimum of 100")
        return cls(agents)

    def random(self) -> Agent:
        return choice(self._agents)

    def get(self, agent_id: int) -> Agent:
        for agent in self._agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(f"Agent {agent_id} not found")


DEFAULT_AGENTS_PATH = Path(__file__).resolve().parent.parent / "agents" / "agents.json"

default_agent_pool = AgentPool.from_json(DEFAULT_AGENTS_PATH)
