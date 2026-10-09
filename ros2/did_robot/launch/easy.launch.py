"""Gazebo + static map + agent; mock disabled by default, start gated by coordinates."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import PythonExpression
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
import json


def map_transform(context):
    config=json.loads(Path(LaunchConfiguration('config_file').perform(context)).read_text())
    return [Node(package='tf2_ros',executable='static_transform_publisher',name='map_to_odom',
                 arguments=['--x',str(config['odom_x']),'--y',str(config['odom_y']),'--z','0',
                            '--yaw',str(config['odom_yaw']),'--pitch','0','--roll','0',
                            '--frame-id','map','--child-frame-id','odom'],
                 parameters=[{'use_sim_time':True}],output='screen')]


def generate_launch_description():
    tb=Path(get_package_share_directory('turtlebot3_gazebo'))
    did=Path(get_package_share_directory('did_robot'))
    arg=lambda name:LaunchConfiguration(name)
    boolean=lambda name:ParameterValue(arg(name),value_type=bool)
    common={'use_sim_time':True,'config_file':arg('config_file'),'seed':ParameterValue(arg('seed'),value_type=int),'scenario':arg('scenario')}
    return LaunchDescription([
        DeclareLaunchArgument('config_file',default_value=str(did/'config/agent.json')),
        DeclareLaunchArgument('map_file',default_value=str(did/'maps/map.yaml')),
        DeclareLaunchArgument('start_world',default_value='true'),
        DeclareLaunchArgument('headless',default_value='false'),
        DeclareLaunchArgument('start_agent',default_value='true'),
        DeclareLaunchArgument('mock_judge',default_value='false'),
        DeclareLaunchArgument('coordinates_verified',default_value='false'),
        DeclareLaunchArgument('autostart',default_value='false'),
        DeclareLaunchArgument('seed',default_value='1'),
        DeclareLaunchArgument('scenario',default_value='easy'),
        DeclareLaunchArgument('mode',default_value='baseline'),
        DeclareLaunchArgument('planner_mode',default_value='algorithmic'),
        # Exposed because DOCX and current upstream defaults disagree; verify actual world/odom.
        DeclareLaunchArgument('x_pose',default_value='-2.0'),
        DeclareLaunchArgument('y_pose',default_value='-0.5'),
        OpaqueFunction(function=map_transform),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(tb/'launch/turtlebot3_world.launch.py')),
             condition=IfCondition(PythonExpression(["'",arg('start_world'),"' == 'true' and '",arg('headless'),"' == 'false'"])),
             launch_arguments={'use_sim_time':'true','x_pose':arg('x_pose'),'y_pose':arg('y_pose')}.items()),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(did/'launch/world_headless.launch.py')),
             condition=IfCondition(PythonExpression(["'",arg('start_world'),"' == 'true' and '",arg('headless'),"' == 'true'"])),
             launch_arguments={'x_pose':arg('x_pose'),'y_pose':arg('y_pose')}.items()),
        Node(package='nav2_map_server',executable='map_server',name='map_server',
             parameters=[{'use_sim_time':True,'yaml_filename':arg('map_file'),'frame_id':'map'}],output='screen'),
        Node(package='nav2_lifecycle_manager',executable='lifecycle_manager',name='map_lifecycle',
             parameters=[{'use_sim_time':True,'autostart':True,'node_names':['map_server']}],output='screen'),
        Node(package='did_robot',executable='mock_judge',name='did_mock_judge',
             parameters=[common],condition=IfCondition(arg('mock_judge')),output='screen'),
        Node(package='did_robot',executable='agent',name='did_agent',condition=IfCondition(arg('start_agent')),parameters=[common,
             {'coordinates_verified':boolean('coordinates_verified'),'autostart':boolean('autostart'),'mode':arg('mode'),'planner_mode':arg('planner_mode')}],output='screen'),
    ])
