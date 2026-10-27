"""启动目标识别 + 导航目标发送两个节点。

前置条件（请先启动）：
  1. ros2 launch ugv_nav nav.launch.py use_rviz:=true   （导航 + AMCL 定位，并在 RViz 里设定初始位姿）
  2. ros2 launch ugv_nav_target oak_camera_aligned.launch.py   （相机，USB2 总线记得带 usb2 参数）

启动时可指定目标颜色（覆盖 yaml 默认红色），例：
  ros2 launch ugv_nav_target target_nav.launch.py target_color:=green
可选: red(默认,双区间) / green / blue / yellow / custom(用 yaml 里的值)
运行中可用 rqt_reconfigure 或 ros2 param set /target_detector hsv_ranges 在线改阈值。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

COLORS = {
    "red": [0, 120, 70, 10, 255, 255, 170, 120, 70, 180, 255, 255],
    "green": [35, 80, 80, 85, 255, 255],
    "blue": [100, 120, 70, 130, 255, 255],
    "yellow": [20, 120, 120, 40, 255, 255],
}


def launch_setup(context, *args, **kwargs):
    config = os.path.join(
        get_package_share_directory("ugv_nav_target"), "config", "target_detect.yaml"
    )
    color = LaunchConfiguration("target_color").perform(context)
    hsv = COLORS.get(color)
    if color != "custom" and hsv is None:
        print(f"[target_nav] 警告: 未知 target_color '{color}'，回退 red")
        hsv = COLORS["red"]
    params = [config] + ([{"hsv_ranges": hsv}] if hsv else [])
    if color == "custom":
        print("[target_nav] target_color=custom，使用 yaml 中的 hsv_ranges")

    return [
        Node(
            package="ugv_nav_target",
            executable="target_detector",
            name="target_detector",
            parameters=params,
            output="screen",
        ),
        Node(
            package="ugv_nav_target",
            executable="goal_sender",
            name="goal_sender",
            parameters=[config],
            output="screen",
        ),
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "target_color",
                default_value="red",
                description="目标颜色: red/green/blue/yellow/custom",
            ),
            OpaqueFunction(function=launch_setup),
        ]
    )
