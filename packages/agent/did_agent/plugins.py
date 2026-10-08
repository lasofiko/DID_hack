"""Explicit team plugin factory; server environment only, never browser supplied."""
import importlib
import os
import re
import asyncio
from contextlib import AsyncExitStack

def load_plugin(variable,methods):
    specification=os.environ.get(variable,'')
    if not specification:return None
    if not re.fullmatch(r'did_ml\.[A-Za-z0-9_.]+:[A-Za-z_][A-Za-z0-9_]*',specification):
        raise ValueError('Plugin must be did_ml.module:factory')
    module,name=specification.split(':');instance=getattr(importlib.import_module(module),name)()
    if not all(callable(getattr(instance,m,None)) for m in methods):raise ValueError('Plugin does not implement contract')
    return instance


class PlannerRuntime:
    """Own one optional planner/client on the mission loop, including shutdown.

    Both the original plain Planner factory and an async context manager yielding
    a Planner are supported. No model request occurs during initialization.
    """
    def __init__(self, log, factory=None):
        self.log = log
        self.factory = factory or (lambda: load_plugin('DID_PLANNER_FACTORY', []))
        self.planner = None
        self._stack = None
        self._lock = asyncio.Lock()

    async def open(self):
        async with self._lock:
            if self.planner is not None:
                return self.planner
            stack = AsyncExitStack()
            try:
                instance = self.factory()
                if instance is None:
                    return None
                if callable(getattr(instance, '__aenter__', None)):
                    instance = await stack.enter_async_context(instance)
                if not callable(getattr(instance, 'propose', None)):
                    raise ValueError('Planner contract unavailable')
                self.planner, self._stack = instance, stack
                return instance
            except BaseException as exc:
                try:
                    await stack.aclose()
                except Exception as cleanup:
                    self.log('Planner cleanup failed: ' + type(cleanup).__name__)
                if not isinstance(exc, Exception):
                    raise
                # Factory/provider exceptions may include credentials or URLs.
                self.log('Planner unavailable; Algorithmic fallback: ' + type(exc).__name__)
                return None

    async def close(self):
        async with self._lock:
            stack, self._stack = self._stack, None
            self.planner = None
            if stack is not None:
                await stack.aclose()
