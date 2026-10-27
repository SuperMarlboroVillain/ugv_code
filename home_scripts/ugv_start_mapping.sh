#!/bin/bash
# UGV 一键建图：确保容器运行 -> 终端开三个标签页：建图 / 键盘遥控 / 保存地图
CT=ugv_jetson_ros_humble

if ! docker ps -q -f "name=^/${CT}$" | grep -q .; then
  echo "启动 Docker 容器 ${CT} ..."
  docker start "$CT"
  sleep 3
fi

gnome-terminal --window --title="建图" --maximize -- bash -lc \
  '~/ugv_ros.sh ros2 launch ugv_auto stage1_mapping_joy.launch.py; \
   echo; echo "===== 建图已退出。没保存的话去「保存地图」标签页已经来不及了，下次记得先保存 ====="; \
   echo "按回车关闭本窗口"; read' \
  --tab --title="键盘遥控" -- bash -lc \
  'sleep 5; ~/ugv_ros.sh ros2 run ugv_auto keyboard_teleop' \
  --tab --title="保存地图" -- bash -lc \
  'echo "扫完后到本标签页按【回车】保存正式地图（保存前不要停建图！）"; read; \
   ~/ugv_ros.sh bash /home/ws/ugv_ws/save_2d_cartographer_map.sh; \
   echo; echo "已保存到 ugv_ws/src/ugv_main/ugv_nav/maps/（map.pgm / map.yaml / map.pbstream）"; \
   echo "现在可以去「建图」标签页 Ctrl+C 退出。按回车关闭本标签页"; read'
