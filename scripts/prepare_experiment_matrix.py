"""Generate an immutable 60-run plan; never start Docker, ROS or a mission."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'experiments/plans/final-matrix.json')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing campaign plan; choose a new output path')
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    files = ['configs/agent.json','configs/maps/map.yaml','configs/maps/map.pgm',
             'packages/agent/did_agent/navigation.py','packages/agent/did_agent/mission.py',
             'packages/ml/did_ml/energy.py']
    config = json.loads((ROOT/'configs/agent.json').read_text())
    plan = dict(schema_version=1, status='PLANNED_NOT_EXECUTED',
                runtime_source_revision=revision, file_sha256={p:sha(p) for p in files},
                scientific_config=config, demo_profile=False,
                initial_battery=60, mission_timeout_s=config['mission_timeout'],
                external_observer_deadline_s=config['mission_timeout']+45,
                ros_domain_id=42, concurrent_missions=1,
                metrics=['delivered','collected','battery_remaining','battery_used',
                         'route_length_m','elapsed_wall_s','elapsed_sim_s',
                         'replans_full_journal','return_success','safety_events'],
                llm_classification=['PROVIDER_EXECUTED','MIXED_FALLBACK','FALLBACK_ONLY',
                                    'PROVIDER_FAILED','NOT_VERIFIED'], runs=[])
    for scenario, seed, planner in itertools.product(['easy','medium','hard'],range(1,6),['algorithmic','llm']):
        # Alternate pair order by seed to reduce systematic warm-up/order bias.
        modes = ['baseline','adaptive'] if seed % 2 else ['adaptive','baseline']
        for mode in modes:
            run_id = f'{scenario}-seed{seed}-{planner}-{mode}'
            plan['runs'].append(dict(run_id=run_id,
                pair_id=f'{scenario}-seed{seed}-{planner}',
                session=dict(scenario=scenario,seed=seed,mode=mode,planner_mode=planner),
                result_json=f'experiments/runs/full-matrix/CAMPAIGN/{run_id}.json',
                status='NOT_RUN'))
    assert len(plan['runs']) == 60
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(plan,indent=2)+'\n')
    print(f'Prepared {len(plan["runs"])} runs; executed 0: {args.output}')

if __name__ == '__main__':
    main()
