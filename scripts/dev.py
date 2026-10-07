from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/backend"))

if __name__ == "__main__":
    from did_backend.main import run
    run()
