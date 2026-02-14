"""LiteLLM-backed LLM provider with full tool-calling support.

LiteLLM gives us a single ``acompletion`` call that fans out to 100+
providers (OpenAI, Anthropic, Gemini, Groq, Ollama …).  This module
converts our internal dataclasses ↔ the OpenAI-style dicts that LiteLLM
expects, and handles streaming / error paths.
"""

from __future__ import annotations

import json
from typing import Any

import litellm
from loguru import logger

from .base import (
    BaseLLMProvider,
    LLMResponse,
    ToolCallRequests,
)


class LiteLLMProvider(BaseLLMProvider):
    """Concrete provider that delegates to ``litellm.acompletion``."""

    name: str = "litellm"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        """Optional overrides for the LiteLLM client.

        LiteLLM reads keys from env vars automatically
        (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, …).
        Only pass ``api_key`` / ``api_base`` if you need an explicit override
        (e.g. a proxy, or a single shared key).
        """
        self._api_key = api_key
        self._api_base = api_base
        self._default_headers = default_headers or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def generate_response(
        self,
        model: str,
        messages: list[dict],
        tools: list[Any] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Call the LLM via LiteLLM and return a structured ``LLMResponse``.

        Tool-calling flow
        -----------------
        1. If ``tools`` is provided the model *may* return one or more
           ``tool_calls`` instead of (or alongside) text content.
        2. The caller (agent loop) should execute them, append ``tool``
           messages with the results, and call ``generate_response`` again.
        3. Repeat until the model replies with pure text (no tool calls).
        """
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._default_headers:
            kwargs["extra_headers"] = self._default_headers

        logger.debug(
            "LiteLLM request | model={} msgs={} tools={}",
            model,
            len(messages),
            len(tools) if tools else 0,
        )

        try:
            response = await litellm.acompletion(**kwargs)
        except litellm.exceptions.AuthenticationError as exc:
            logger.error("LiteLLM auth error for model={}: {}", model, exc)
            raise
        except litellm.exceptions.RateLimitError as exc:
            logger.warning("LiteLLM rate-limited for model={}: {}", model, exc)
            raise
        except Exception as exc:
            logger.error("LiteLLM call failed for model={}: {}", model, exc)
            raise

        return self._parse_response(response)

    # ------------------------------------------------------------------
    # Internal: build LiteLLM-compatible dicts
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Convert a LiteLLM ``ModelResponse`` → ``LLMResponse``."""
        if not response.choices:
            raise RuntimeError("LLM returned no choices")

        choice = response.choices[0]
        assistant_msg = choice.message

        # --- Text content ---
        content = getattr(assistant_msg, "content", None)

        # --- Tool calls ---
        tool_calls: list[ToolCallRequests] = []
        raw_tool_calls = getattr(assistant_msg, "tool_calls", None)
        if raw_tool_calls:
            for tc in raw_tool_calls:
                # Parse arguments; LiteLLM returns them as a JSON string
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Failed to parse tool-call arguments for {}: {}",
                        tc.function.name,
                        tc.function.arguments,
                    )
                    arguments = {}

                tool_calls.append(
                    ToolCallRequests(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        # --- Usage ---
        usage: dict[str, int] = {}
        raw_usage = getattr(response, "usage", None)
        if raw_usage:
            usage = {
                "prompt_tokens": getattr(raw_usage, "prompt_tokens", 0),
                "completion_tokens": getattr(raw_usage, "completion_tokens", 0),
                "total_tokens": getattr(raw_usage, "total_tokens", 0),
            }

        logger.debug(
            "LiteLLM response | content_len={} tool_calls={} usage={}",
            len(content) if content else 0,
            len(tool_calls),
            usage,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )
