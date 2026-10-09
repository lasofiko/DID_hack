"""One final authorized live request, then exact offline replay; no physical IO."""
import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_planner_integration import fixture
from did_ml.context import PlannerConfig
from did_ml.runtime import llm_planner
from did_ml.settings import LLMSettings
from did_ml.journal import ReplayProvider
from did_ml.provider import ProviderError
from dotenv import dotenv_values

async def main(env_file, output_directory):
    output_directory.mkdir(parents=True, exist_ok=True)
    TRACE = output_directory / 'trace.jsonl'
    OUTPUT = output_directory / 'evidence.json'
    if TRACE.exists() or OUTPUT.exists():
        raise RuntimeError('Probe already attempted; do not repeat the request')
    env = {**dotenv_values(env_file, interpolate=False), **os.environ}
    if not all(env.get(k) for k in ('DID_LLM_ENDPOINT', 'DID_LLM_MODEL', 'DID_LLM_API_KEY')):
        raise RuntimeError('Missing existing configuration')
    settings = replace(LLMSettings.from_env(env), timeout=10, max_tokens=256)
    count = 0
    async with llm_planner(settings, PlannerConfig(provider_attempts=1), journal_path=TRACE) as planner:
        provider = planner.provider

        class Budgeted:
            async def complete(self, prompt):
                nonlocal count
                if count:
                    raise ProviderError('probe_budget_exhausted', retryable=False)
                count += 1
                return await provider.complete(prompt)

        planner.provider = Budgeted()
        manager, _, search, obs = fixture()
        manager.config = replace(manager.config, planner_timeout=12)
        manager.planner = planner
        started = time.monotonic()
        goal = await manager.choose(obs, search)
        source = manager.planner_source
        elapsed = round(time.monotonic() - started, 3)
        manager._planner_result(False, 'SYNTHETIC_PROBE_NOT_EXECUTED')
        evidence = dict(requests=count, manager_source=source, action=goal['action'],
                        elapsed_s=elapsed, physical_execution=False,
                        result_recorded=any(e['kind'] == 'result' for e in planner.history))
        session = planner.session_id
    evidence['client_closed'] = provider._client.is_closed
    replay_manager, replay_planner, replay_search, replay_obs = fixture(ReplayProvider(TRACE, session_id=session))
    replay_planner.config = replace(replay_planner.config, provider_attempts=1)
    replay_goal = await replay_manager.choose(replay_obs, replay_search)
    evidence['replay_exact'] = replay_goal == goal and replay_manager.planner_source == 'LLM'
    replay_manager._planner_result(False, 'SYNTHETIC_PROBE_NOT_EXECUTED')
    evidence['accepted'] = source == 'LLM' and evidence['replay_exact']
    OUTPUT.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.env_file, args.output_dir))
    except Exception as exc:
        print(json.dumps({'status': 'probe_error', 'error_type': type(exc).__name__}))
        sys.exit(1)
