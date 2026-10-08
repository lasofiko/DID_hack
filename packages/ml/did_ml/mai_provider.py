"""Async Chat Completions adapter for MAI; routing must be confirmed on their API."""
import asyncio
import json
import httpx

from .provider import SYSTEM_PROMPT, ProviderError
from .settings import LLMSettings


class MAIProvider:
    def __init__(self, settings: LLMSettings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout), follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        await self._client.aclose()

    async def complete(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
            raise ProviderError("invalid_prompt", retryable=False)
        # Planner already adds SYSTEM_PROMPT; separate trusted instructions from data.
        prefix = SYSTEM_PROMPT + "\nPUBLIC_CONTEXT_JSON:\n"
        content = prompt[len(prefix):] if prompt.startswith(prefix) else prompt
        payload = {
            "model": self.settings.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": content}],
            "stream": False,
            "max_tokens": self.settings.max_tokens,
        }
        if self.settings.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.settings.thinking != "omit":
            payload["thinking"] = {"type": self.settings.thinking}
        try:
            # Wall-clock deadline also bounds slow trickling responses.
            async with asyncio.timeout(self.settings.timeout):
                async with self._client.stream(
                    "POST", self.settings.endpoint, json=payload,
                    headers={"Authorization": f"Bearer {self.settings.api_key}",
                             "Accept": "application/json"},
                ) as response:
                    if response.status_code != 200:
                        status = response.status_code
                        code = {401: "authentication", 403: "forbidden", 404: "endpoint_or_model",
                                429: "rate_limited"}.get(status, "http_error")
                        # Do not immediately hammer a rate-limited or misconfigured API.
                        raise ProviderError(code, retryable=status in {408, 500, 502, 503, 504}, status_code=status)
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 256_000:
                            raise ProviderError("response_too_large", retryable=False)
                return self._extract(bytes(chunks))
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderError("timeout", retryable=True) from None
        except httpx.HTTPError:
            raise ProviderError("transport", retryable=True) from None

    @staticmethod
    def _extract(raw: bytes) -> str:
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ProviderError("incomplete_response", retryable=True)
            message = choice["message"]
            if message.get("tool_calls") or message.get("refusal"):
                raise ProviderError("unsupported_response", retryable=True)
            content = message["content"]
            if not isinstance(content, str) or not content.strip() or len(content) > 12000:
                raise ProviderError("empty_or_invalid_content", retryable=True)
            # reasoning_content is deliberately ignored; only final content is a subgoal.
            return content
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError):
            raise ProviderError("invalid_envelope", retryable=True) from None
