from __future__ import annotations

from typing import Iterable, List, Set

from telethon.tl.types import Message


def extract_usernames(messages: Iterable[Message], limit: int) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()
    for msg in messages:
        if msg.sender and getattr(msg.sender, "bot", False):
            continue
        username = None
        if getattr(msg.sender, "username", None):
            username = msg.sender.username
        elif msg.message:
            parts = [part for part in msg.message.split() if part.startswith("@")]  # naive
            if parts:
                username = parts[0].lstrip("@")
        if username and username not in seen:
            seen.add(username)
            found.append(username)
        if len(found) >= limit:
            break
    return found
