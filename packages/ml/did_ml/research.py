"""Explicit hypothesis registry: formulations are supplied by the research module."""
from copy import deepcopy
import re
from did_core.types import JournalEntry
from .context import nonnegative


class HypothesisRegistry:
    def __init__(self):
        self._active = {}
        self._used = set()

    @property
    def active(self) -> list[dict]:
        return deepcopy(list(self._active.values()))

    @property
    def ids(self) -> set[str]:
        return set(self._active)

    def register(self, hypothesis_id: str, statement: str, expected: str, sim_time: float) -> JournalEntry:
        nonnegative(sim_time, "sim_time")
        if not isinstance(hypothesis_id, str) or not re.fullmatch(r"H[0-9]{1,6}", hypothesis_id):
            raise ValueError("Use hypothesis ids H1..H999999")
        if hypothesis_id in self._used or len(self._used) >= 1000 or len(self._active) >= 20:
            raise ValueError("Duplicate hypothesis or registry capacity exceeded")
        for text in (statement, expected):
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
                raise ValueError("Statement and expected observation must contain 1..1000 characters")
        self._active[hypothesis_id] = {"id": hypothesis_id, "statement": statement,
                                       "expected": expected, "created_at": sim_time}
        self._used.add(hypothesis_id)
        return {"sim_time": sim_time, "hypothesis_id": hypothesis_id, "stage": "hypothesis",
                "text": statement + " Expected: " + expected}

    def conclude(self, hypothesis_id: str, evidence: str, conclusion: str, sim_time: float) -> list[JournalEntry]:
        nonnegative(sim_time, "sim_time")
        if hypothesis_id not in self._active or sim_time < self._active[hypothesis_id]["created_at"]:
            raise ValueError("Unknown hypothesis or conclusion predates registration")
        for text in (evidence, conclusion):
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
                raise ValueError("Evidence and conclusion must contain 1..2000 characters")
        del self._active[hypothesis_id]
        return [{"sim_time": sim_time, "hypothesis_id": hypothesis_id, "stage": stage, "text": text}
                for stage, text in (("observation", evidence), ("conclusion", conclusion))]
