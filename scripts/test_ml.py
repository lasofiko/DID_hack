"""Run ML tests without editable install or external dependencies."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
for package in ("contracts", "ml"):
    sys.path.insert(0, str(root / "packages" / package))
if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_ml*.py")
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
