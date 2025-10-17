from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace


class DummyEvent(SimpleNamespace):
    pass


class DummyEvents(ModuleType):
    def __init__(self):
        super().__init__("telethon.events")
        self.NewMessage = DummyEvent
        self.CallbackQuery = DummyEvent


class DummyButtonModule(ModuleType):
    def __init__(self):
        super().__init__("telethon.Button")

    def inline(self, text, data):  # type: ignore[override]
        return (text, data)


class DummyErrors(ModuleType):
    def __init__(self, name: str):
        super().__init__(name)

        class FloodWaitError(Exception):
            def __init__(self, request=None, seconds: int = 0):
                super().__init__("FloodWait")
                self.seconds = seconds

        class UserDeactivatedError(Exception):
            def __init__(self, request=None):
                super().__init__("UserDeactivated")

        class AuthKeyError(Exception):
            def __init__(self, request=None):
                super().__init__("AuthKeyError")

        class SessionPasswordNeededError(Exception):
            def __init__(self, request=None):
                super().__init__("Password needed")

        self.FloodWaitError = FloodWaitError
        self.UserDeactivatedError = UserDeactivatedError
        self.AuthKeyError = AuthKeyError
        self.SessionPasswordNeededError = SessionPasswordNeededError


class DummyTLTypes(ModuleType):
    class Message(SimpleNamespace):
        pass


class DummyTL(ModuleType):
    def __init__(self):
        super().__init__("telethon.tl")
        self.types = DummyTLTypes("telethon.tl.types")
        self.custom = ModuleType("telethon.tl.custom")
        self.custom.Button = DummyButtonModule()


class DummyTelegramClient:
    def __init__(self, *args, **kwargs):
        self.session = SimpleNamespace(save=lambda: "session")

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def send_message(self, *args, **kwargs):
        pass

    async def send_file(self, *args, **kwargs):
        pass

    def add_event_handler(self, *args, **kwargs):
        pass

    async def run_until_disconnected(self):
        pass

    def start(self, *args, **kwargs):
        return self

    def iter_messages(self, *args, **kwargs):  # pragma: no cover
        async def _gen():
            if False:
                yield None
        return _gen()


def install_telethon_stub() -> None:
    telethon = ModuleType("telethon")
    telethon.TelegramClient = DummyTelegramClient
    telethon.Button = DummyButtonModule()
    telethon.events = DummyEvents()
    telethon.errors = DummyErrors("telethon.errors")
    telethon.tl = DummyTL()
    sessions_module = ModuleType("telethon.sessions")

    class StringSession:
        def __init__(self, value: str | None = None):
            self.value = value or ""

        def save(self) -> str:
            return self.value or "session"

    sessions_module.StringSession = StringSession
    telethon.sessions = sessions_module
    sys.modules.setdefault("telethon", telethon)
    sys.modules.setdefault("telethon.events", telethon.events)
    sys.modules.setdefault("telethon.errors", telethon.errors)
    sys.modules.setdefault("telethon.Button", telethon.Button)
    sys.modules.setdefault("telethon.tl", telethon.tl)
    sys.modules.setdefault("telethon.tl.custom", telethon.tl.custom)
    sys.modules.setdefault("telethon.tl.types", telethon.tl.types)
    sys.modules.setdefault("telethon.sessions", sessions_module)


class DummyAsyncpg(ModuleType):
    async def create_pool(self, dsn):  # pragma: no cover - stub
        raise RuntimeError("asyncpg is not available in test stub")


sys.modules.setdefault("asyncpg", DummyAsyncpg("asyncpg"))


class DummyAiosqlite(ModuleType):
    class Row(dict):
        pass

    async def connect(self, *args, **kwargs):  # pragma: no cover - stub
        raise RuntimeError("aiosqlite stub")


sys.modules.setdefault("aiosqlite", DummyAiosqlite("aiosqlite"))


install_telethon_stub()
