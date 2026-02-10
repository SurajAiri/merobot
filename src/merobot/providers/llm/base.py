from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequests:
    id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class ToolCallResults:
    id: str
    result: Any
    error: str | None = None


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequests] = field(default_factory=list)
    results: list[ToolCallResults] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class BaseLLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate_response(
        self,
        model: str,
        message: str,
        message_history: list[tuple[str, str]] = [],
        tool_requests: list[ToolCallRequests] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Chat response generation method. Should return content and tool calls if any.

        Args:
            model: The name of the LLM model to use for generation.
            message: The current user message to respond to.
            message_history: A list of tuples containing past messages and responses for context.
            tool_requests: A list of tool call requests that the LLM should make based on the message and history.
            max_tokens: The maximum number of tokens to generate in the response.
            temperature: The sampling temperature for response generation, controlling randomness.
        return:
            An LLMResponse object containing the generated content and any tool calls.
        """  # noqa: E501
        pass
