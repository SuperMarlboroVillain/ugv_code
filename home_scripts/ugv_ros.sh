#!/bin/bash
# 进入 UGV 的 ROS2 容器（自动 source 好环境），之后直接敲 ros2 命令即可
# 用法: ~/ugv_ros.sh            进容器交互 shell
#       ~/ugv_ros.sh ros2 launch ugv_auto stage1_mapping_joy.launch.py
# 注意: docker exec 默认不把宿主环境带进容器，GUI 相关变量这里显式转发：
#       DISPLAY/XAUTHORITY（RViz、cv2.imshow 需要；授权配合宿主机 xhost +SI:localuser:root）
TTY=""
if [ -t 0 ] && [ -t 1 ]; then TTY="-it"; fi
ENVF=""
[ -n "${DISPLAY:-}" ] && ENVF="$ENVF -e DISPLAY=$DISPLAY"
[ -n "${XAUTHORITY:-}" ] && ENVF="$ENVF -e XAUTHORITY=$XAUTHORITY"
if [ $# -eq 0 ]; then
  docker exec $ENVF $TTY ugv_jetson_ros_humble bash -lc \
    'source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && exec bash'
else
  docker exec $ENVF $TTY ugv_jetson_ros_humble bash -lc \
    "source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && $*"
fi
