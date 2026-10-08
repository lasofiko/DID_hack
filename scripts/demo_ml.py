"""Run a short offline planning example from the repository root."""
from pathlib import Path
import asyncio
import sys

root = Path(__file__).resolve().parents[1]
for package in ("contracts", "ml"):
    sys.path.insert(0, str(root / "packages" / package))
if __name__ == "__main__":
    from did_ml.demo import main
    asyncio.run(main())
