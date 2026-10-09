"""Opt-in demo cruise gain, bounded approach and unchanged scientific profile."""
from pathlib import Path
from dataclasses import replace
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from did_agent import AgentConfig
from did_agent.navigation import MotionController

class DemoMotionTests(unittest.TestCase):
    def test_demo_gain_and_scientific_limits(self):
        root = Path(__file__).resolve().parents[1]
        scientific = AgentConfig.load(root/'configs/agent.json')
        demo = AgentConfig.load(root/'configs/agent-demo.json')
        self.assertEqual((scientific.max_linear, scientific.max_angular), (.12, .4))
        self.assertEqual((demo.max_linear, demo.max_angular), (.18, .8))
        pose, target = dict(x=0., y=0.), dict(x=.11, y=0.)
        self.assertGreater(MotionController(demo).command(pose, 0., target)[0],
                           MotionController(scientific).command(pose, 0., target)[0])

    def test_approach_does_not_cross_target_over_two_ticks(self):
        config = replace(AgentConfig(), linear_approach_gain=1.6, control_period=.5)
        v, w = MotionController(config).command(dict(x=0.,y=0.),0.,dict(x=.1,y=0.))
        self.assertEqual(w, 0.)
        self.assertLessEqual(v*2*config.control_period, .1-config.goal_tolerance*.5)
        self.assertEqual(MotionController(config).command(dict(x=0.,y=0.),0.,dict(x=.08,y=0.)),(0.,0.))

    def test_turn_has_no_translation(self):
        controller = MotionController(AgentConfig())
        self.assertEqual(controller.command(dict(x=0.,y=0.),0.,dict(x=0.,y=1.))[0],0.)
