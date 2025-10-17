from types import SimpleNamespace

from senderbot.extraction import extract_usernames


class DummyMessage(SimpleNamespace):
    pass


def make_msg(text: str, username: str | None = None, bot: bool = False):
    sender = SimpleNamespace(username=username, bot=bot)
    return DummyMessage(message=text, sender=sender)


def test_extract_usernames_unique_order():
    messages = [
        make_msg("hello @alice", None),
        make_msg("hi", "bob"),
        make_msg("@alice again", None),
        make_msg("bot message", "helperbot", bot=True),
        make_msg("hello", "carol"),
    ]
    result = extract_usernames(messages, limit=10)
    assert result == ["alice", "bob", "carol"]


def test_extract_usernames_limit():
    messages = [make_msg("hi", "user1"), make_msg("hi", "user2"), make_msg("hi", "user3")]
    result = extract_usernames(messages, limit=2)
    assert result == ["user1", "user2"]
