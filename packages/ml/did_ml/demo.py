"""Small integration example, no robot/model/network and no hidden samples."""
import asyncio
import json
from .context import Candidate, PlanningContext
from .planner import ResearchPlanner


async def main():
    planner = ResearchPlanner()
    obs = {"sim_time": 1.0, "pose": {"x": 0.0, "y": 0.0}, "battery": 60.0,
           "signal": 0.2, "pose_time": 1.0, "battery_time": 1.0,
           "signal_time": 1.0, "scan_time": 1.0, "obstacle_ahead": False}
    planner.set_context(PlanningContext(1, 0, 0, home_energy=0,
        candidates=(Candidate("frontier-1", 1, 0, 2, 2), Candidate("frontier-2", 0, 2, 4, 4))))
    goal = await planner.propose(obs)
    print(json.dumps(goal, ensure_ascii=False, indent=2))
    # This example reports a rejection; it does not claim that the robot moved.
    planner.record_result(goal, {"success": False, "message": "Example backend rejection"}, 1)
    print(json.dumps(await planner.propose(obs, "Previous target rejected"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
