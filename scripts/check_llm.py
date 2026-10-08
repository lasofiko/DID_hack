"""Explicit live API smoke test using synthetic public data, never robot commands."""
from pathlib import Path
import asyncio
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ("contracts", "ml"):
    sys.path.insert(0, str(ROOT / "packages" / package))


async def main() -> int:
    from dotenv import load_dotenv
    from did_ml import Candidate, PlanningContext
    from did_ml.runtime import llm_planner

    load_dotenv(ROOT / ".env", override=False)
    try:
        async with llm_planner() as planner:
            obs = {"sim_time": 1, "pose": {"x": 0, "y": 0}, "battery": 60,
                   "signal": .2, "pose_time": 1, "battery_time": 1,
                   "signal_time": 1, "scan_time": 1, "obstacle_ahead": False}
            planner.set_context(PlanningContext(1, 0, 0, 0,
                (Candidate("test-frontier", 1, 0, 2, 2),)))
            goal = await planner.propose(obs)
            used_model = planner.history[-1]["source"] == "provider"
            print(json.dumps({"source": "llm" if used_model else "offline_fallback", "goal": goal},
                             ensure_ascii=False, indent=2))
            if not used_model:
                print(json.dumps([event for event in planner.history if event["kind"] == "provider_error"]))
                print("LLM response was not accepted; inspect endpoint, credentials and supported parameters.")
            return 0 if used_model else 1
    except ValueError:
        print("Invalid or missing DID_LLM_* settings. Check .env.example; no request sent.")
        return 2


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except ImportError:
        print('Install ML dependencies: python -m pip install -e ".[ml]"')
        sys.exit(2)
