"""启动 OAK-D Lite 相机（深度与 RGB 对齐版本）。

与 ugv_vision/oak_d_lite.launch.py 的区别：
  - 使用本包的 oak_d_lite_aligned.yaml，开启 stereo.i_align_depth，
    使 /oak/stereo/image_raw 的深度与 /oak/rgb/image_rect 逐像素对齐，
    供目标识别节点解算目标三维坐标。

话题与官方 launch 完全一致（name 仍为 oak），可同时与其它使用
/oak 话题的节点共存。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LoadComposableNodes
from launch_ros.descriptions import ComposableNode
from launch.conditions import UnlessCondition


def launch_setup(context, *args, **kwargs):
    name = LaunchConfiguration("name").perform(context)
    depthai_prefix = get_package_share_directory("depthai_ros_driver")
    params_file = LaunchConfiguration("params_file")

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(depthai_prefix, "launch", "camera.launch.py")
            ),
            launch_arguments={
                "name": name,
                "parent_frame": "3d_camera_link",
                "params_file": params_file,
                "use_rviz": "False",
            }.items(),
        ),
        LoadComposableNodes(
            condition=UnlessCondition(LaunchConfiguration("rectify_rgb")),
            target_container=name + "_container",
            composable_node_descriptions=[
                ComposableNode(
                    package="image_proc",
                    plugin="image_proc::RectifyNode",
                    name="rectify_color_node",
                    remappings=[
                        ("image", name + "/rgb/image_raw"),
                        ("camera_info", name + "/rgb/camera_info"),
                        ("image_rect", name + "/rgb/image_rect"),
                    ],
                )
            ],
        ),
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("name", default_value="oak"),
            DeclareLaunchArgument(
                "params_file",
                default_value=os.path.join(
                    get_package_share_directory("ugv_nav_target"),
                    "config",
                    "oak_d_lite_aligned.yaml",
                ),
            ),
            DeclareLaunchArgument("rectify_rgb", default_value="False"),
            OpaqueFunction(function=launch_setup),
        ]
    )
