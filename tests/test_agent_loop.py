"""Integration tests for AgentLoop — verifies the full message flow.

Tests the consume → LLM → tool loop → respond pipeline with mocked LLM.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from merobot.agents.loop import AgentLoop
from merobot.handler.message_bus import MessageBus
from merobot.handler.messages import InboundMessage
from merobot.handler.session.session import SessionManager
from merobot.providers.llm.base import LLMResponse, ToolCallRequests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def session():
    return SessionManager(max_history=50)


@pytest.fixture
def agent_loop(bus, session):
    with patch("merobot.agents.loop.get_config") as mock_config:
        # Minimal config stub
        defaults = AsyncMock()
        defaults.provider = "litellm"
        defaults.model = "gpt-3.5-turbo"
        defaults.max_tokens = 2048
        defaults.temperature = 0.7

        config = AsyncMock()
        config.agent.defaults = defaults
        config.providers = {
            "litellm": AsyncMock(api_key="test-key")
        }
        mock_config.return_value = config

        loop = AgentLoop(message_bus=bus, session_manager=session)
        return loop


def _make_inbound(text: str = "hello", chat_id: str = "42") -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        content=text,
        sender_id="7",
        chat_id=chat_id,
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimpleResponse:
    """LLM returns plain text — no tool calls."""

    @pytest.mark.asyncio
    async def test_text_response_publishes_outbound(self, agent_loop, bus):
        # Mock LLM to return a simple text response
        agent_loop.llm.generate_response = AsyncMock(
            return_value=LLMResponse(content="Hello! How can I help?")
        )

        # Put an inbound message on the bus
        msg = _make_inbound("hi there")
        await bus.publish_inbound(msg)

        # Run the agent loop for one iteration
        task = asyncio.create_task(agent_loop.run())
        try:
            # Wait for the outbound message to appear
            outbound = await asyncio.wait_for(bus.outbound.get(), timeout=5.0)

            assert outbound.channel == "telegram"
            assert outbound.content == "Hello! How can I help?"
            assert outbound.chat_id == "42"
            assert outbound.recipient_id == "7"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_session_records_user_and_assistant(self, agent_loop, bus, session):
        agent_loop.llm.generate_response = AsyncMock(
            return_value=LLMResponse(content="Sure thing!")
        )

        await bus.publish_inbound(_make_inbound("do something"))
        task = asyncio.create_task(agent_loop.run())
        try:
            await asyncio.wait_for(bus.outbound.get(), timeout=5.0)

            history = session.get_history("42")
            assert len(history) == 2
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "do something"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "Sure thing!"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class TestToolCallingFlow:
    """LLM requests tool calls, then responds with text."""

    @pytest.mark.asyncio
    async def test_tool_call_then_text(self, agent_loop, bus, session):
        # First call: LLM requests a tool
        tool_response = LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequests(
                    id="call_123",
                    name="date_time",
                    arguments={},
                )
            ],
        )
        # Second call: LLM returns text
        text_response = LLMResponse(content="The current time is 3:00 PM.")

        agent_loop.llm.generate_response = AsyncMock(
            side_effect=[tool_response, text_response]
        )

        # Mock the tool execution
        agent_loop.tool_registry.execute = AsyncMock(
            return_value="2026-02-14 15:00:00"
        )

        await bus.publish_inbound(_make_inbound("what time is it?"))
        task = asyncio.create_task(agent_loop.run())
        try:
            outbound = await asyncio.wait_for(bus.outbound.get(), timeout=5.0)

            assert outbound.content == "The current time is 3:00 PM."

            # LLM was called twice
            assert agent_loop.llm.generate_response.call_count == 2

            # Tool was executed
            agent_loop.tool_registry.execute.assert_awaited_once_with(
                "date_time", {}
            )

            # Session has user + assistant(tool_call) + tool + assistant(text)
            history = session.get_history("42")
            roles = [m["role"] for m in history]
            assert roles == ["user", "assistant", "tool", "assistant"]
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class TestMaxIterationsGuard:
    """LLM keeps requesting tools past the limit."""

    @pytest.mark.asyncio
    async def test_stops_after_max_iterations(self, agent_loop, bus):
        # Always return tool calls
        tool_response = LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequests(id="call_n", name="date_time", arguments={})
            ],
        )
        agent_loop.llm.generate_response = AsyncMock(return_value=tool_response)
        agent_loop.tool_registry.execute = AsyncMock(return_value="result")

        await bus.publish_inbound(_make_inbound("loop forever"))
        task = asyncio.create_task(agent_loop.run())
        try:
            outbound = await asyncio.wait_for(bus.outbound.get(), timeout=10.0)

            # Should have stopped and returned a fallback
            assert "limit" in outbound.content.lower() or outbound.content is not None

            # LLM was called MAX_TOOL_ITERATIONS times
            from merobot.agents.loop import MAX_TOOL_ITERATIONS
            assert agent_loop.llm.generate_response.call_count == MAX_TOOL_ITERATIONS
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class TestSessionManager:
    """Unit tests for SessionManager."""

    def test_add_and_get_history(self, session):
        session.add_message("c1", "user", "hello")
        session.add_message("c1", "assistant", "hi there")

        history = session.get_history("c1")
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi there"}

    def test_separate_chats(self, session):
        session.add_message("c1", "user", "msg1")
        session.add_message("c2", "user", "msg2")

        assert len(session.get_history("c1")) == 1
        assert len(session.get_history("c2")) == 1

    def test_clear(self, session):
        session.add_message("c1", "user", "hello")
        session.clear("c1")
        assert session.get_history("c1") == []

    def test_trimming(self):
        sm = SessionManager(max_history=3)
        for i in range(5):
            sm.add_message("c1", "user", f"msg {i}")
        history = sm.get_history("c1")
        assert len(history) == 3
        assert history[0]["content"] == "msg 2"

    def test_system_messages_not_trimmed(self):
        sm = SessionManager(max_history=2)
        sm.add_message("c1", "system", "you are helpful")
        for i in range(5):
            sm.add_message("c1", "user", f"msg {i}")
        history = sm.get_history("c1")
        assert history[0]["role"] == "system"
        assert len([m for m in history if m["role"] != "system"]) == 2
