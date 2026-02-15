import httpx
from loguru import logger

from merobot.providers.llm.base import BaseLLMProvider, LLMResponse


class LlmApiProvider(BaseLLMProvider):
    async def generate_response(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        params = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools is not None:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient() as client:
                headers = self._default_headers.copy()
                headers["Content-Type"] = "application/json"
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                response = await client.post(
                    f"{self._api_base}/chat/completions",
                    json=params,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                import json

                with open("debug_llm_response.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return LLMResponse(
                    content=data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", ""),
                    tool_calls=data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("tool_calls", []),
                    usage=data.get("usage", {}),
                    raw_response=data,
                )
        except Exception as e:
            logger.error(f"LLM API request failed: {e}")
            raise
