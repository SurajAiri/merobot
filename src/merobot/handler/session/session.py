"""In-memory session manager — stores conversation history per chat_id.

Each session is a list of OpenAI-format message dicts:
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

Designed for single-event-loop asyncio; no locking needed.
"""

from __future__ import annotations

from loguru import logger


class SessionManager:
    """Manages per-chat conversation history in memory."""

    def __init__(self, max_history: int = 50) -> None:
        """
        Args:
            max_history: Maximum messages to keep per chat (oldest trimmed first).
                         System messages are never trimmed.
        """
        self._sessions: dict[str, list[dict]] = {}
        self._max_history = max_history

    def get_history(self, chat_id: str) -> list[dict]:
        """Return the full message history for a chat (copy)."""
        return list(self._sessions.get(chat_id, []))

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str | None = None,
        **kwargs,
    ) -> None:
        """Append a message to the chat history.

        Args:
            chat_id: Unique chat/session identifier.
            role:    One of "user", "assistant", "tool", "system".
            content: Message text (may be None for tool-call-only assistant turns).
            **kwargs: Extra fields (e.g. tool_calls, tool_call_id, name).
        """
        if chat_id not in self._sessions:
            self._sessions[chat_id] = []

        message: dict = {"role": role}
        if content is not None:
            message["content"] = content
        message.update(kwargs)

        self._sessions[chat_id].append(message)
        self._trim(chat_id)

        logger.trace(
            "Session {} | added {} message (total: {})",
            chat_id,
            role,
            len(self._sessions[chat_id]),
        )

    def clear(self, chat_id: str) -> None:
        """Clear conversation history for a chat."""
        self._sessions.pop(chat_id, None)
        logger.debug("Session {} cleared", chat_id)

    @property
    def active_sessions(self) -> int:
        """Number of chats with stored history."""
        return len(self._sessions)

    def _trim(self, chat_id: str) -> None:
        """Keep only the last ``max_history`` non-system messages."""
        msgs = self._sessions[chat_id]
        # Separate system messages (keep all) from conversation messages
        system = [m for m in msgs if m["role"] == "system"]
        conversation = [m for m in msgs if m["role"] != "system"]

        if len(conversation) > self._max_history:
            trimmed = len(conversation) - self._max_history
            conversation = conversation[trimmed:]
            logger.debug(
                "Session {} | trimmed {} old messages", chat_id, trimmed
            )

        self._sessions[chat_id] = system + conversation
