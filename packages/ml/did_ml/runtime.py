"""Own the API client lifecycle alongside a planner instance."""
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from .context import PlannerConfig
from .mai_provider import MAIProvider
from .planner import ResearchPlanner
from .settings import LLMSettings
from .journal import JsonlJournal


@asynccontextmanager
async def llm_planner(settings: LLMSettings | None = None, config: PlannerConfig | None = None,
                      *, journal_path: Path | None = None):
    settings = settings or LLMSettings.from_env()
    # One timeout setting, no hidden shorter deadline inherited from the offline default.
    config = replace(config or PlannerConfig(), provider_timeout=settings.timeout)
    journal = JsonlJournal(journal_path, secrets=(settings.api_key,)) if journal_path else None
    if journal:
        journal.write({"kind": "provider_config", "model": settings.model,
                       "endpoint": settings.endpoint, "timeout": settings.timeout,
                       "max_tokens": settings.max_tokens, "thinking": settings.thinking,
                       "json_mode": settings.json_mode})
    async with MAIProvider(settings) as provider:
        yield ResearchPlanner(config=config, provider=provider, journal=journal)
