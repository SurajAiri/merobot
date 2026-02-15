"""Agent loop — consumes inbound messages, runs LLM with tool loop, publishes responses.

This is the core processing engine of merobot. It sits between the
MessageBus (inbound side) and the LLM provider, orchestrating:
    1. Message consumption from the bus
    2. Context assembly (system prompt + history)
    3. LLM calls with iterative tool execution
    4. Response publishing back to the bus
"""

from __future__ import annotations

import json

from loguru import logger

from merobot.agents.context import AgentContextBuilder
from merobot.agents.tools import ToolRegistry
from merobot.config import get_config
from merobot.handler.message_bus import MessageBus
from merobot.handler.messages import InboundMessage, OutboundMessage
from merobot.handler.session.session import SessionManager
from merobot.providers.llm import LiteLLMProvider
from merobot.tools import (
    CodeExecutorTool,
    DateTimeTool,
    FileReadTool,
    FileWriteTool,
    SQLiteQueryTool,
    SubAgentTool,
    WebScrapeTool,
    WebSearchTool,
)

MAX_TOOL_ITERATIONS = 10


class AgentLoop:
    """Main agent loop — bridges the MessageBus and the LLM."""

    def __init__(
        self,
        message_bus: MessageBus,
        session_manager: SessionManager,
    ) -> None:
        self.config = get_config()
        self.message_bus = message_bus
        self.session = session_manager

        # LLM setup
        self.model_config = self.config.agent.defaults
        provider_config = self.config.providers[self.model_config.provider]
        self.llm = LiteLLMProvider(provider_config)

        # Context builder
        self.context_builder = AgentContextBuilder(session_manager)

        # Tools
        self._register_tools()

    def _register_tools(self) -> None:
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(DateTimeTool())
        self.tool_registry.register(FileReadTool())
        self.tool_registry.register(FileWriteTool())
        self.tool_registry.register(WebScrapeTool())
        self.tool_registry.register(WebSearchTool())
        self.tool_registry.register(CodeExecutorTool())
        self.tool_registry.register(SQLiteQueryTool())
        self.tool_registry.register(
            SubAgentTool(
                llm=self.llm,
                tool_registry=self.tool_registry,
                model=self.model_config.model,
                max_tokens=self.model_config.max_tokens,
                temperature=self.model_config.temperature,
            )
        )

    async def run(self) -> None:
        """Main loop — runs forever as an asyncio task.

        Flow per message:
            1. Consume inbound message from bus
            2. Record user message in session
            3. Build context (system + history)
            4. LLM call loop (with tool execution)
            5. Record assistant reply in session
            6. Publish outbound message to bus
        """
        logger.info("AgentLoop started — waiting for messages")

        while True:
            try:
                msg: InboundMessage = await self.message_bus.consume_inbound()
                logger.info(
                    "Processing message from {} in chat {}",
                    msg.sender_id,
                    msg.chat_id,
                )
                response_text = await self._process_message(msg)
                await self._send_response(msg, response_text)

            except Exception as exc:
                logger.error("AgentLoop error: {}", exc, exc_info=True)

    async def _process_message(self, msg: InboundMessage) -> str:
        """Run the LLM with tool loop and return the final text response."""

        # Handle /clear command
        if msg.metadata.get("command") == "clear":
            self.session.clear(msg.chat_id)
            return "🗑️ Conversation history cleared. Let's start fresh!"

        # 1. Build user content (text + media context if present)
        content = msg.content or ""
        if msg.media:
            media_type = msg.metadata.get("media_type", "file")
            media_desc = ", ".join(msg.media)
            content = (
                f"{content}\n\n"
                f"[User attached {media_type} file(s) saved at: {media_desc}. "
                f"You can read or analyze these files using your tools.]"
            ).strip()

        # 2. Record user message in session
        self.session.add_message(msg.chat_id, "user", content)

        # 3. Build context
        messages = self.context_builder.build(msg.chat_id)

        # 3. Tool definitions for the LLM
        tool_definitions = self.tool_registry.get_definitions()
        llm_response = None

        # 4. LLM call loop
        for iteration in range(MAX_TOOL_ITERATIONS):
            logger.debug(
                "LLM call iteration {} for chat {}", iteration + 1, msg.chat_id
            )

            llm_response = await self.llm.generate_response(
                model=self.model_config.model,
                messages=messages,
                tools=tool_definitions if tool_definitions else None,
                max_tokens=self.model_config.max_tokens,
                temperature=self.model_config.temperature,
            )

            # If no tool calls, we have the final answer
            if not llm_response.has_tool_calls:
                content = llm_response.content or "I'm not sure how to respond to that."
                self.session.add_message(msg.chat_id, "assistant", content)
                return content

            # --- Tool execution ---
            # Append the assistant's tool-call message to context
            assistant_msg: dict = {"role": "assistant"}
            if llm_response.content:
                assistant_msg["content"] = llm_response.content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in llm_response.tool_calls
            ]
            messages.append(assistant_msg)
            self.session.add_message(
                msg.chat_id,
                "assistant",
                llm_response.content,
                tool_calls=assistant_msg["tool_calls"],
            )

            # Execute each tool and append results
            for tc in llm_response.tool_calls:
                logger.info("Executing tool: {} ({})", tc.name, tc.id)
                result = await self.tool_registry.execute(tc.name, tc.arguments)
                logger.debug("Tool {} result: {:.200}", tc.name, result)

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                }
                messages.append(tool_msg)
                self.session.add_message(
                    msg.chat_id,
                    "tool",
                    result,
                    tool_call_id=tc.id,
                    name=tc.name,
                )

        # Max iterations reached — return whatever we have
        logger.warning(
            "Max tool iterations ({}) reached for chat {}",
            MAX_TOOL_ITERATIONS,
            msg.chat_id,
        )
        content = llm_response.content if llm_response else None
        fallback = (
            content or "I ran into a limit processing your request. Please try again."
        )
        self.session.add_message(msg.chat_id, "assistant", fallback)
        return fallback

    async def _send_response(self, original: InboundMessage, text: str) -> None:
        """Publish the response back to the outbound queue."""
        outbound = OutboundMessage(
            channel=original.channel,
            content=text,
            recipient_id=original.sender_id,
            chat_id=original.chat_id,
        )
        await self.message_bus.publish_outbound(outbound)
        logger.debug("Published response to chat {}", original.chat_id)
