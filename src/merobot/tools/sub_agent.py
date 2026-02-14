"""Sub-agent spawner tool — delegates tasks to a separate LLM call.

The sub-agent gets its own message thread and can use the same tools
(except itself, to prevent infinite recursion). It runs a mini tool
loop and returns the final text response as the tool result.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from merobot.providers.llm.base import BaseLLMProvider
from merobot.tools.base import BaseTool

MAX_SUB_AGENT_ITERATIONS = 5

SUB_AGENT_SYSTEM_PROMPT = """\
You are a sub-agent spawned by MeroBot to handle a specific task.
Complete the task using the tools available to you.
Be thorough but concise in your response.
Return only the final result — no commentary about being a sub-agent.\
"""


class SubAgentTool(BaseTool):
    """Spawn a sub-agent to handle a delegated task."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        tool_registry: Any,  # ToolRegistry — avoid circular import
        model: str = "gpt-3.5-turbo",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> None:
        """
        Args:
            llm: The LLM provider to use for sub-agent calls.
            tool_registry: The ToolRegistry instance (sub_agent will be excluded).
            model: Model identifier for sub-agent LLM calls.
            max_tokens: Max tokens for sub-agent responses.
            temperature: Temperature for sub-agent LLM calls.
        """
        self._llm = llm
        self._tool_registry = tool_registry
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def name(self) -> str:
        return "sub_agent"

    @property
    def description(self) -> str:
        return (
            "Spawn a sub-agent to handle a delegated task. "
            "Useful for breaking complex tasks into smaller parts, "
            "or when you need to run a separate line of investigation. "
            "The sub-agent has access to the same tools (except spawning more sub-agents). "
            "Returns the sub-agent's final text response."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Clear description of the task for the sub-agent.",
                    "minLength": 1,
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional background information or context to help "
                        "the sub-agent understand the task better."
                    ),
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task: str = kwargs.get("task", "").strip()
        context: str = kwargs.get("context", "").strip()

        if not task:
            return "Error: 'task' parameter is required."

        logger.info(f"Sub-agent spawned for task: {task[:100]}")

        # Build sub-agent message thread
        messages: list[dict] = [
            {"role": "system", "content": SUB_AGENT_SYSTEM_PROMPT},
        ]
        if context:
            messages.append({"role": "user", "content": f"Context: {context}"})
        messages.append({"role": "user", "content": task})

        # Get tool definitions excluding this tool (prevent recursion)
        tool_defs = [
            t for t in self._tool_registry.get_definitions()
            if t["function"]["name"] != self.name
        ]

        # Mini tool loop
        for iteration in range(MAX_SUB_AGENT_ITERATIONS):
            logger.debug(f"Sub-agent iteration {iteration + 1}")

            llm_response = await self._llm.generate_response(
                model=self._model,
                messages=messages,
                tools=tool_defs if tool_defs else None,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )

            # If no tool calls, return the text
            if not llm_response.has_tool_calls:
                result = llm_response.content or "Sub-agent completed but produced no output."
                logger.info(f"Sub-agent completed in {iteration + 1} iteration(s)")
                return result

            # Process tool calls
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

            for tc in llm_response.tool_calls:
                logger.info(f"Sub-agent executing tool: {tc.name}")
                result = await self._tool_registry.execute(tc.name, tc.arguments)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                })

        # Max iterations reached
        logger.warning("Sub-agent max iterations reached")
        content = llm_response.content if llm_response else None
        return content or "Sub-agent reached its iteration limit without a final answer."
