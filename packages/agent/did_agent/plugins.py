"""Explicit team plugin factory; server environment only, never browser supplied."""
import importlib
import os
import re

def load_plugin(variable,methods):
    specification=os.environ.get(variable,'')
    if not specification:return None
    if not re.fullmatch(r'did_ml\.[A-Za-z0-9_.]+:[A-Za-z_][A-Za-z0-9_]*',specification):
        raise ValueError('Plugin must be did_ml.module:factory')
    module,name=specification.split(':');instance=getattr(importlib.import_module(module),name)()
    if not all(callable(getattr(instance,m,None)) for m in methods):raise ValueError('Plugin does not implement contract')
    return instance
