"""Server-side factories. Creating a factory never sends an API request."""
from .planner import ResearchPlanner


def create_planner():
    return ResearchPlanner()


def create_llm_planner():
    """Managed existing MAI client; enter/exit on the mission's asyncio loop."""
    import os
    from pathlib import Path
    from uuid import uuid4
    from .runtime import llm_planner

    directory = os.environ.get('DID_LLM_JOURNAL_DIR')
    journal = Path(directory) / (uuid4().hex + '.jsonl') if directory else None
    return llm_planner(journal_path=journal)
