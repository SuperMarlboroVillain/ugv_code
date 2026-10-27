"""第二阶段：Nav2 导航 + 单目视觉识别 + 自动接近目标。

用法：
  ros2 launch ugv_auto stage2_nav_vision.launch.py use_rviz:=true

流程：先在 RViz 中点 '2D Pose Estimate' 给出初始位姿，
然后把红色目标（默认 15 cm 宽，可用 config/target.yaml 改）放在视野内，
机器人会自动规划路径开到目标前 0.35 m 处。

use_camera:=false 用于离线测试（可用合成图像注入替代真实相机）。
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_rviz = LaunchConfiguration('use_rviz', default='true')
    use_camera = LaunchConfiguration('use_camera', default='true')
    params_file = LaunchConfiguration('params_file', default=os.path.join(
        get_package_share_directory('ugv_auto'), 'config', 'target.yaml'))

    ugv_model = SetEnvironmentVariable('UGV_MODEL', 'ugv_beast')
    lidar_model = SetEnvironmentVariable('LDLIDAR_MODEL', 'ld19')

    # 导航（内部已包含底盘 bringup）
    nav = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ugv_nav'),
            'launch', 'nav.launch.py')),
        launch_arguments={
            'use_localization': 'amcl',
            'use_localplan': 'teb',
            'use_rviz': use_rviz}.items())

    # USB 相机
    camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ugv_vision'),
            'launch', 'camera.launch.py')),
        condition=IfCondition(use_camera))

    detector = Node(
        package='ugv_auto', executable='mono_detector', name='mono_detector',
        parameters=[params_file],
        output='screen')
    manager = Node(
        package='ugv_auto', executable='approach_manager', name='approach_manager',
        parameters=[params_file],
        output='screen')

    return LaunchDescription([
        ugv_model, lidar_model, nav, camera, detector, manager,
    ])
