from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Tool Definitions (what you tell the LLM it *can* call)
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    """Schema describing a tool the LLM may invoke.

    Attributes:
        name:        Unique tool identifier (e.g. "get_weather").
        description: Human-readable purpose – the LLM uses this to decide
                     when the tool is relevant.
        parameters:  JSON-Schema dict describing accepted arguments.
                     Must follow the OpenAI function-calling schema, e.g.:
                     {
                         "type": "object",
                         "properties": {
                             "city": {"type": "string", "description": "..."}
                         },
                         "required": ["city"]
                     }
    """

    name: str
    description: str
    parameters: dict[str, Any]


# ---------------------------------------------------------------------------
# Tool Calls (what the LLM *asks* you to execute)
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM.

    Attributes:
        id:        Provider-assigned call ID (needed to match results back).
        name:      Name of the tool to invoke.
        arguments: Parsed argument dict.
    """

    id: str
    name: str
    arguments: dict[str, Any]


# ---------------------------------------------------------------------------
# Conversation Messages
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """One turn in the conversation history.

    Roles follow the OpenAI convention used by LiteLLM:
        * ``system``    – system prompt / persona.
        * ``user``      – end-user input.
        * ``assistant`` – model output (may contain tool_calls).
        * ``tool``      – result returned to the model after a tool call.

    Attributes:
        role:         One of "system", "user", "assistant", "tool".
        content:      Text payload (``None`` for pure tool-call assistant turns).
        tool_calls:   Populated on **assistant** messages that request tools.
        tool_call_id: Populated on **tool** messages; matches a ``ToolCall.id``
                      so the LLM knows which result belongs to which request.
        name:         Optional tool name on **tool** messages.
    """

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


# ---------------------------------------------------------------------------
# LLM Response
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Unified response returned by every provider.

    After calling ``generate_response`` you check ``has_tool_calls``:
        * **True**  → the agent loop should execute the requested tools,
                      append ``tool`` messages, and call the LLM again.
        * **False** → ``content`` holds the final text answer.

    Attributes:
        content:       The model's text reply (may be ``None`` when only
                       tool calls are returned).
        tool_calls:    Tool invocations the model wants executed.
        usage:         Token-usage dict straight from the provider
                       (``{"prompt_tokens": …, "completion_tokens": …, …}``).
        raw_response:  The unprocessed provider response for debugging.
    """

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


# ---------------------------------------------------------------------------
# Abstract Provider
# ---------------------------------------------------------------------------


class BaseLLMProvider(ABC):
    """Interface every LLM back-end must implement.

    Subclasses only need to fill in ``generate_response``.  The rest of the
    agent loop (tool execution, retries, planning) lives one layer above.
    """

    name: str = "base"

    @abstractmethod
    async def generate_response(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a conversation to the LLM and return its response.

        Args:
            model:       Model identifier.  For LiteLLM this is the
                         ``provider/model`` slug, e.g. ``"openai/gpt-4o"``,
                         ``"anthropic/claude-sonnet-4-20250514"``.
            messages:    Full conversation history (system + user + assistant
                         + tool messages).
            tools:       Tool schemas the model is allowed to call.
                         Pass ``None`` or ``[]`` to disable tool use.
            max_tokens:  Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            An ``LLMResponse`` with content and/or tool calls.
        """
        ...
