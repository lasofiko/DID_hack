"""Local, append-only trace; replay uses recorded final text, never reasoning tokens."""
from hashlib import sha256
from collections import deque
import json
from pathlib import Path
from typing import Protocol
from .provider import ProviderError


class JournalWriteError(RuntimeError):
    """Audit storage failure: refuse further execution, never provider fallback."""
    def __init__(self):
        super().__init__("ML journal write failed; stop and restore logging before continuing")


class EventSink(Protocol):
    def write(self, event: dict) -> None: ...


def prompt_hash(prompt: str) -> str:
    return sha256(prompt.encode("utf-8")).hexdigest()


class JsonlJournal:
    def __init__(self, path: Path, *, secrets: tuple[str, ...] = ()):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError, TypeError):
            raise JournalWriteError() from None
        self._secrets = tuple(s for s in secrets if s)

    def write(self, event: dict) -> None:
        def redact(value):
            if isinstance(value, str):
                for secret in self._secrets:
                    value = value.replace(secret, "[REDACTED]")
                return value
            if isinstance(value, dict):
                return {k: redact(v) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(v) for v in value]
            return value
        try:
            line = json.dumps(redact(event), ensure_ascii=False, allow_nan=False)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        except (OSError, ValueError, TypeError):
            raise JournalWriteError() from None


class ReplayProvider:
    """Strict replay of one session's successful HTTP responses, including invalid subgoals."""
    def __init__(self, path: Path, *, session_id: str):
        with Path(path).open(encoding="utf-8") as stream:
            self._records = deque([entry for line in stream if line.strip()
                                  for entry in [json.loads(line)]
                                  if entry.get("session_id") == session_id and entry.get("kind") == "llm_exchange"])

    async def complete(self, prompt: str) -> str:
        if not self._records:
            raise ProviderError("replay_exhausted", retryable=False)
        record = self._records[0]
        if record["prompt_sha256"] != prompt_hash(prompt):
            raise ProviderError("replay_prompt_mismatch", retryable=False)
        self._records.popleft()
        return record["response"]
