"""In-memory tracker for pending "Sign in" messages.

Once a Telegram user becomes linked, the auth middleware pops any tracked
messages and strips their inline keyboards so the stale button disappears.
"""

_pending: dict[int, list[tuple[int, int]]] = {}


def remember(telegram_id: int, chat_id: int, message_id: int) -> None:
    _pending.setdefault(telegram_id, []).append((chat_id, message_id))


def pop_all(telegram_id: int) -> list[tuple[int, int]]:
    return _pending.pop(telegram_id, [])
