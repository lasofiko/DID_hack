"""Repository paths for dependency-free local scripts/tests (not a ROS installation)."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
for directory in ('packages/contracts','packages/agent','packages/environment','packages/ml','apps/backend'):
    sys.path.insert(0,str(ROOT/directory))
