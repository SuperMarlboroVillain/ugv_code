#!/bin/bash
# 进入 UGV 的 ROS2 容器（自动 source 好环境），之后直接敲 ros2 命令即可
# 用法: ~/ugv_ros.sh            进容器交互 shell
#       ~/ugv_ros.sh ros2 launch ugv_auto stage1_mapping_joy.launch.py
TTY=""
if [ -t 0 ] && [ -t 1 ]; then TTY="-it"; fi
if [ $# -eq 0 ]; then
  docker exec $TTY ugv_jetson_ros_humble bash -lc \
    'source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && exec bash'
else
  docker exec $TTY ugv_jetson_ros_humble bash -lc \
    "source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && $*"
fi
