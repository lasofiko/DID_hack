from setuptools import setup
from glob import glob

setup(
    name='did_robot',version='0.1.0',
    packages=['did_robot','did_agent','did_core','did_environment'],
    package_dir={'did_robot':'did_robot','did_agent':'../../packages/agent/did_agent',
                 'did_core':'../../packages/contracts/did_core','did_environment':'../../packages/environment/did_environment'},
    data_files=[('share/ament_index/resource_index/packages',['resource/did_robot']),
                ('share/did_robot',['package.xml']),
                ('share/did_robot/launch',glob('launch/*.launch.py')),
                ('share/did_robot/config',['../../configs/agent.json']),
                ('share/did_robot/maps',glob('../../configs/maps/*'))],
    install_requires=['setuptools'],zip_safe=False,
    maintainer='DID Hack team',maintainer_email='did-hack@example.invalid',
    description='Single TurtleBot3 EASY agent and optional local mock judge',license='Apache-2.0',
    entry_points={'console_scripts':['agent = did_robot.agent_node:main','mock_judge = did_robot.judge_node:main']},
)
