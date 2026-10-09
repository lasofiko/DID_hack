"""Explicit one-request live ML probe; synthetic data, no ROS or robot commands.

Requires an existing endpoint/model/key; prints no credentials or model text.
No automatic retry. Exit 0 means a provider decision passed local validation,
not that a physical mission ran.
"""
import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
for package in ('contracts', 'ml'):
    sys.path.insert(0, str(ROOT / 'packages' / package))


async def probe(env_file):
    from dotenv import dotenv_values
    from did_ml import Candidate, PlanningContext, PlannerConfig
    from did_ml.runtime import llm_planner
    from did_ml.settings import LLMSettings

    env = {**dotenv_values(env_file, interpolate=False), **os.environ}
    required = ('DID_LLM_API_KEY', 'DID_LLM_ENDPOINT', 'DID_LLM_MODEL')
    if not all(env.get(key) for key in required):
        return {'status': 'not_configured', 'requests': 0}
    settings = replace(LLMSettings.from_env(env), timeout=10, max_tokens=256)
    async with llm_planner(settings, PlannerConfig(provider_attempts=1)) as planner:
        provider = planner.provider
        calls = 0

        class Counted:
            async def complete(self, prompt):
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise RuntimeError('Live probe request budget exceeded')
                return await provider.complete(prompt)

        planner.provider = Counted()
        obs = dict(sim_time=1, pose={'x': 0, 'y': 0}, battery=60, signal=.2,
                   pose_time=1, battery_time=1, signal_time=1, scan_time=1,
                   obstacle_ahead=False)
        planner.set_context(PlanningContext(1, 0, 0, 0, (Candidate('synthetic', 1, 0, 2, 2),)))
        started = time.monotonic()
        goal = await planner.propose(obs)
        source = next(e['source'] for e in reversed(planner.history) if e['kind'] == 'proposal')
        # No execution occurred; finalize explicitly as a rejected synthetic probe.
        planner.record_result(goal, {'success': False, 'message': 'SYNTHETIC_PROBE_NOT_EXECUTED'}, 1)
        return {'status': 'accepted' if source == 'provider' else 'fallback',
                'requests': calls, 'source': source, 'action': goal['action'],
                'elapsed_s': round(time.monotonic() - started, 3),
                'errors': [{k: e[k] for k in ('error_type', 'stage', 'code', 'status_code') if k in e}
                           for e in planner.history if e['kind'] == 'provider_error'],
                'physical_execution': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(probe(args.env_file))
    except Exception as exc:
        result = {'status': 'probe_error', 'error_type': type(exc).__name__}
    print(json.dumps(result, ensure_ascii=True))
    sys.exit(0 if result['status'] == 'accepted' else 1)
