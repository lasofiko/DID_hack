"""Official turtlebot3_world assets and spawner, server-only with EGL/OGRE2."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, AppendEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    share=Path(get_package_share_directory('turtlebot3_gazebo'))
    source=lambda file:PythonLaunchDescriptionSource(str(share/'launch'/file))
    return LaunchDescription([
        DeclareLaunchArgument('x_pose',default_value='-2.0'),
        DeclareLaunchArgument('y_pose',default_value='-0.5'),
        AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH',str(share/'models')),
        ExecuteProcess(cmd=['gz','sim','-s','-r',
                            *(['--headless-rendering'] if os.environ.get('RENDER_MODE','egl')!='xvfb' else []),
                            '--render-engine','ogre2','-v','3',
                            str(share/'worlds/turtlebot3_world.world')],output='screen'),
        # Upstream launch appends '/' even for an empty prefix, splitting TF from
        # the DiffDrive plugin's unprefixed odom -> base_footprint edge.
        Node(package='robot_state_publisher',executable='robot_state_publisher',
             parameters=[{'use_sim_time':True,'frame_prefix':'',
                          'robot_description':(share/'urdf'/('turtlebot3_'+os.environ.get('TURTLEBOT3_MODEL','burger')+'.urdf')).read_text()}],
             output='screen'),
        IncludeLaunchDescription(source('spawn_turtlebot3.launch.py'),launch_arguments={
            'x_pose':LaunchConfiguration('x_pose'),'y_pose':LaunchConfiguration('y_pose')}.items()),
    ])
