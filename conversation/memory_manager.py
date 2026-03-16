"""Thread-safe, bounded conversational memory."""

from __future__ import annotations

from threading import RLock
from typing import Dict, List


class MemoryManager:
    """Store recent messages by session without external persistence."""

    def __init__(self, max_messages: int = 12, max_message_chars: int = 2_000):
        self.max_messages = max_messages
        self.max_message_chars = max_message_chars
        self._sessions: Dict[str, List[dict]] = {}
        self._lock = RLock()

    def create_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.setdefault(session_id, [])

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        clean_content = content.strip()[: self.max_message_chars]
        with self._lock:
            history = self._sessions.setdefault(session_id, [])
            history.append({"role": role, "content": clean_content})
            del history[: max(0, len(history) - self.max_messages)]

    def get_history(self, session_id: str) -> List[dict]:
        with self._lock:
            return [message.copy() for message in self._sessions.get(session_id, [])]

    def get_active_context(self, session_id: str) -> List[dict]:
        return self.get_history(session_id)[-self.max_messages :]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

