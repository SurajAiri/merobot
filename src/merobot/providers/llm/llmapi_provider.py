"""Direct HTTP-based LLM provider (OpenAI-compatible API).

Talks to any OpenAI-compatible chat/completions endpoint (Groq, Together,
OpenRouter, vLLM, local models, etc.) via raw HTTP.  Converts the JSON
response into the internal ``LLMResponse`` / ``ToolCallRequests`` dataclasses
so the agent loop can consume tool calls uniformly.
"""

from __future__ import annotations

import json

import httpx
from loguru import logger

from merobot.providers.llm.base import BaseLLMProvider, LLMResponse, ToolCallRequests


class LlmApiProvider(BaseLLMProvider):
    """LLM provider that calls an OpenAI-compatible REST API directly."""

    name: str = "llmapi"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def generate_response(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        # Strip provider slug prefix if present (e.g. "groq/llama3" → "llama3")
        if model.startswith(self.config.slug):
            model = model[len(self.config.slug) + 1 :]

        params: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        url = f"{self._api_base}/chat/completions"

        logger.debug(
            "LlmApi request | url={} model={} msgs={} tools={}",
            url,
            model,
            len(messages),
            len(tools) if tools else 0,
        )

        try:
            async with httpx.AsyncClient() as client:
                headers = self._default_headers.copy()
                headers["Content-Type"] = "application/json"
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"

                response = await client.post(
                    url,
                    json=params,
                    headers=headers,
                    timeout=120.0,
                )

                # --- Surface provider errors clearly ---
                if response.status_code >= 400:
                    try:
                        error_body = response.json()
                    except Exception:
                        error_body = response.text

                    error_msg = (
                        f"LLM API {response.status_code} {response.reason_phrase} "
                        f"for model='{model}' at {url}: {error_body}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                data = response.json()

            return self._parse_response(data)

        except RuntimeError:
            raise  # already logged above
        except Exception as exc:
            logger.error("LLM API request failed: {}", exc)
            raise

    # ------------------------------------------------------------------
    # Internal: parse the OpenAI-compatible JSON response
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_response(data: dict) -> LLMResponse:
        """Convert a raw OpenAI-style JSON dict → ``LLMResponse``."""

        choices = data.get("choices")
        if not choices:
            raise RuntimeError(
                f"LLM API returned no choices: {json.dumps(data)[:500]}"
            )

        message = choices[0].get("message", {})

        # --- Text content ---
        content = message.get("content") or None

        # --- Tool calls ---
        tool_calls: list[ToolCallRequests] = []
        raw_tool_calls = message.get("tool_calls")
        if raw_tool_calls:
            for tc in raw_tool_calls:
                tc_id = tc.get("id", "")
                func = tc.get("function", {})
                tc_name = func.get("name", "")

                # Arguments come as a JSON string from the API
                raw_args = func.get("arguments", "{}")
                try:
                    arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Failed to parse tool-call arguments for {}: {}",
                        tc_name,
                        raw_args,
                    )
                    arguments = {}

                if not tc_name:
                    logger.warning("Skipping tool call with empty name: {}", tc)
                    continue

                tool_calls.append(
                    ToolCallRequests(
                        id=tc_id,
                        name=tc_name,
                        arguments=arguments,
                    )
                )

        # --- Usage ---
        usage: dict[str, int] = {}
        raw_usage = data.get("usage")
        if raw_usage and isinstance(raw_usage, dict):
            usage = {
                "prompt_tokens": raw_usage.get("prompt_tokens", 0),
                "completion_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
            }

        logger.debug(
            "LlmApi response | content_len={} tool_calls={} usage={}",
            len(content) if content else 0,
            len(tool_calls),
            usage,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=data,
        )
