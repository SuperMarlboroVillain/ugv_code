"""第一阶段：手柄遥控 + Cartographer 二维建图。

用法：
  ros2 launch ugv_auto stage1_mapping_joy.launch.py            # 默认不开 RViz（4GB 内存机推荐）
  ros2 launch ugv_auto stage1_mapping_joy.launch.py use_rviz:=true   # 本机开 RViz（占内存，易死机）

前提：USB 接收器/手柄已插入（/dev/input/js0）。遥控建图，结束后用
scripts/save_map.sh 保存地图。意外中断可从 autosave 的 .pbstream 续扫：
  ros2 launch ugv_auto stage1_mapping_joy.launch.py load_state:=/home/ws/ugv_ws/src/ugv_main/ugv_nav/maps/autosave/map_xxx.pbstream
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, TextSubstitution
from launch_ros.actions import Node


def generate_launch_description():
    use_rviz = LaunchConfiguration('use_rviz', default='false')
    load_state = LaunchConfiguration('load_state', default='')
    load_state_arg = DeclareLaunchArgument('load_state', default_value='',
                                           description='崩溃续扫：autosave 目录下 .pbstream 的路径')

    ugv_model = SetEnvironmentVariable('UGV_MODEL', 'ugv_beast')
    lidar_model = SetEnvironmentVariable('LDLIDAR_MODEL', 'ld19')

    # SLAM（内部已包含底盘 bringup：雷达/里程计/TF/驱动）
    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ugv_slam'),
            'launch', 'cartographer.launch.py')),
        launch_arguments={'use_rviz': use_rviz,
                          'load_state': load_state}.items())

    # 手柄驱动 + 遥控映射（ugv_auto 通用节点，任意手柄可用）
    joy_node = Node(
        package='joy', executable='joy_node', name='joy_node',
        parameters=[{'dev': '/dev/input/js0', 'deadzone': 0.1, 'autorepeat_rate': 20.0}])
    joy_ctrl = Node(
        package='ugv_auto', executable='joy_teleop', name='joy_teleop',
        parameters=[{'xspeed_limit': 0.5, 'angular_speed_limit': 1.0}])

    return LaunchDescription([
        ugv_model, lidar_model, load_state_arg, slam, joy_node, joy_ctrl,
    ])
