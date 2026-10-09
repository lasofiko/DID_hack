"""Server-side configuration. Never expose settings or credentials to frontend."""
from dataclasses import dataclass, field
import math
import os
from typing import Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True)
class LLMSettings:
    api_key: str = field(repr=False)
    endpoint: str = "https://api-ai.mai.ru/v1/chat/completions"
    model: str = "deepseek-v4.1-flash"
    timeout: float = 5.0
    max_tokens: int = 512
    json_mode: bool = True
    thinking: str = "disabled"

    def __post_init__(self):
        if not isinstance(self.api_key, str) or not self.api_key.strip() or any(c.isspace() for c in self.api_key):
            raise ValueError("DID_LLM_API_KEY must be a nonempty token without whitespace")
        url = urlsplit(self.endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("DID_LLM_ENDPOINT must be an HTTPS URL without credentials/query/fragment")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("DID_LLM_MODEL is required")
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 120:
            raise ValueError("DID_LLM_TIMEOUT must be in (0, 120]")
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens <= 8192:
            raise ValueError("DID_LLM_MAX_TOKENS must be in [1, 8192]")
        if type(self.json_mode) is not bool or self.thinking not in {"disabled", "enabled", "omit"}:
            raise ValueError("Invalid JSON mode or thinking setting")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMSettings":
        env = os.environ if env is None else env
        try:
            json_mode = env.get("DID_LLM_JSON_MODE", "true").lower()
            if json_mode not in {"true", "false"}:
                raise ValueError
            return cls(
                api_key=env.get("DID_LLM_API_KEY", ""),
                endpoint=env.get("DID_LLM_ENDPOINT", cls.endpoint),
                model=env.get("DID_LLM_MODEL", cls.model),
                timeout=float(env.get("DID_LLM_TIMEOUT", "5")),
                max_tokens=int(env.get("DID_LLM_MAX_TOKENS", "512")),
                json_mode=json_mode == "true",
                thinking=env.get("DID_LLM_THINKING", "disabled"),
            )
        except (ValueError, TypeError):
            # Environment values, including accidental credentials, must not leak.
            raise ValueError("Invalid LLM configuration; check DID_LLM_* in .env.example") from None
