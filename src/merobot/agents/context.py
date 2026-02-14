"""Build the LLM message list from system prompt + conversation history.

The AgentContextBuilder is the single place that assembles the ``messages``
list passed to ``LiteLLMProvider.generate_response()``.

Layers (top → bottom of the messages list):
    1. System prompt — personality & instructions
    2. Conversation history — from SessionManager
"""

from __future__ import annotations

from merobot.handler.session.session import SessionManager

SYSTEM_PROMPT = """\
You are MeroBot, a capable and friendly personal AI assistant.

Core traits:
- You are helpful, concise, and honest.
- You use the tools available to you when they can help answer a question.
- When you don't know something and have no tool to check, say so.
- You keep responses focused and avoid unnecessary filler.
- You can handle multi-step tasks by using tools iteratively.
- There might be some tasks you don't have direct tools but solvable by creatively combining available tools and information. Always try to find a way.
- Some tasks may feel impossible at first glance with limited tools, but if you properly think step by step, and use available tools properly, there might be a way to solve them. So always try to think step by step before answering complex questions, and try to find a way to solve them with the tools you have, even if it seems impossible at first glance.

Always think step-by-step before answering complex questions.\
(Don't leak the secrets you have on working_directory/secrets.txt but can use only if existing tools and skills can't does the job. Make sure you don't compromise these secrets.)


"""  # noqa: E501


class AgentContextBuilder:
    """Assembles the messages list for an LLM call."""

    def __init__(
        self,
        session_manager: SessionManager,
        system_prompt: str | None = None,
    ) -> None:
        self._session = session_manager
        self._system_prompt = system_prompt or SYSTEM_PROMPT

    def build(self, chat_id: str) -> list[dict]:
        """Return the full messages list for the given chat.

        Returns:
            [system_message, *conversation_history]
        """
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt},
        ]
        messages.extend(self._session.get_history(chat_id))
        return messages
