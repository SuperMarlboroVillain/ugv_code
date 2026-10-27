#!/bin/bash
# UGV 键盘遥控一键启动：确保容器运行 -> 开一个终端窗口运行 keyboard_teleop
CT=ugv_jetson_ros_humble

if ! docker ps -q -f "name=^/${CT}$" | grep -q .; then
  echo "启动 Docker 容器 ${CT} ..."
  docker start "$CT"
  sleep 3
fi

gnome-terminal --maximize --title="键盘遥控" -- bash -lc \
  '~/ugv_ros.sh ros2 run ugv_auto keyboard_teleop; \
   echo; echo "===== 遥控已退出，按回车关闭本窗口 ====="; read'
