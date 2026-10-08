"""Stage-1 offline suite: explicitly skip complete kinematic mission runs.

--root supports immutable baseline exports without switching the user's checkout.
No live HTTP clients, ROS nodes, Gazebo launches or scenario-runner scripts.
"""
import argparse
import json
from pathlib import Path
import sys
import unittest

FULL_MISSIONS = {
    'test_complete_easy_multiple_seeds',
    'test_official_map_corner_return_after_early_signal_search',
    'test_failed_collect_not_counted_and_not_spammed',
    'test_services_proxy_forbids_private_access',
    'test_no_signal_cannot_use_hidden_targets_to_collect',
    'test_learning_retries_same_search_objective',
}


def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test


def skip_mission():
    raise unittest.SkipTest('Complete kinematic mission excluded from stage 1')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / 'scripts'))
    for package in ('contracts', 'agent', 'environment', 'ml'):
        sys.path.insert(0, str(root / 'packages' / package))
    sys.path.insert(0, str(root / 'apps' / 'backend'))
    top = str(root) if (root / 'tests' / '__init__.py').exists() else None
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), top_level_dir=top)
    for test in cases(suite):
        if test._testMethodName in FULL_MISSIONS:
            setattr(test, test._testMethodName, skip_mission)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = dict(root=str(root), total=result.testsRun,
        passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        failures=[t.id() for t, _ in result.failures], errors=[t.id() for t, _ in result.errors],
        skipped=[{'test': t.id(), 'reason': reason} for t, reason in result.skipped])
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    sys.exit(not result.wasSuccessful())
