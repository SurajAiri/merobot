from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from merobot.config import ProviderConfig


@dataclass
class ToolCallRequests:
    """A single tool invocation requested by the LLM.

    Attributes:
        id:        Provider-assigned call ID (needed to match results back).
        name:      Name of the tool to invoke.
        arguments: Parsed argument dict.
    """

    id: str
    name: str
    arguments: dict[str, Any]


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
        tool_calls:    Tool calls the model requested to be executed.
        usage:         Token-usage dict straight from the provider
                       (``{"prompt_tokens": …, "completion_tokens": …, …}``).
        raw_response:  The unprocessed provider response for debugging.
    """

    content: str | None
    tool_calls: list[ToolCallRequests] = field(default_factory=list)
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

    def __init__(self, config: ProviderConfig) -> None:
        """Initialise the provider from a resolved ``ProviderConfig``.

        The config object already contains the API key (resolved from
        env vars / secret vault) and optional ``api_base`` override.
        """
        self.config = config
        self._api_key = config.api_key
        self._api_base = config.api_base or None
        self._default_headers: dict[str, str] = {}

    @abstractmethod
    async def generate_response(
        self,
        model: str,
        messages: list[
            dict
        ],  # {"role": "system|user|assistant|tool", "content": str, …}
        tools: list[dict]
        | None = None,  # todo: match tool schema definition to ToolDefinition
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a conversation to the LLM and return its response.

        Args:
            model:       Model identifier.  For LiteLLM this is the
                         ``provider/model`` slug, e.g. ``"openai/gpt-4o"``,
                         ``"anthropic/claude-sonnet-4-20250514"``.
            messages:    Full conversation history (system + user + assistant + tool).
                         Each message is a dict with at least 'role' and 'content',
                         plus any provider-specific fields (e.g. 'tool_call_id' for tools).
            tools:       Tool schemas the model is allowed to call.
                         Pass ``None`` or ``[]`` to disable tool use.
            max_tokens:  Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            An ``LLMResponse`` with content and/or tool calls.
        """
        ...
