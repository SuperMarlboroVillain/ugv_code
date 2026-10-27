from launch import LaunchDescription
from launch_ros.actions import Node
import os
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
from launch.conditions import IfCondition, UnlessCondition
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration

def generate_launch_description():

    # Declare launch argument for whether to launch RViz2
    use_rviz_arg = DeclareLaunchArgument('use_rviz', default_value='false',
                                     description='Whether to launch RViz2')
    load_state_arg = DeclareLaunchArgument('load_state', default_value='',
                                     description='崩溃续扫：autosave 目录下 .pbstream 的路径')
    # 4GB 内存机：RViz 用低耗配置（5fps、无 RobotModel），原版 slam_2d 仍可选
    rviz_config_arg = DeclareLaunchArgument('rviz_config', default_value='slam_2d_lowmem',
                                     description='RViz 配置：slam_2d_lowmem(推荐)/slam_2d')

    # Include launch description for bringing up the lidar
    bringup_lidar_launch = IncludeLaunchDescription(PythonLaunchDescriptionSource(
        [os.path.join(get_package_share_directory('ugv_bringup'), 'launch'),
         '/bringup_lidar.launch.py']),
        launch_arguments={
            'use_rviz': LaunchConfiguration('use_rviz'),
            'rviz_config': LaunchConfiguration('rviz_config'),
        }.items()
    )
            
    # Include launch description for robot pose publisher
    robot_pose_publisher_launch = IncludeLaunchDescription(PythonLaunchDescriptionSource(
        [os.path.join(get_package_share_directory('robot_pose_publisher'), 'launch'),
         '/robot_pose_publisher_launch.py'])
    ) 
        
    # Include launch description for cartographer
    cartographer_launch = IncludeLaunchDescription(PythonLaunchDescriptionSource(
        [os.path.join(get_package_share_directory('cartographer'), 'launch'),
         '/mapping.launch.py']),
        launch_arguments={'load_state': LaunchConfiguration('load_state')}.items())
    
    # Return launch description
    return LaunchDescription([
        use_rviz_arg,
        load_state_arg,
        rviz_config_arg,
        bringup_lidar_launch,
        robot_pose_publisher_launch,
        cartographer_launch
    ])
