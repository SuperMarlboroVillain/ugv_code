#!/bin/bash
# UGV 保存地图一键执行：确保容器运行 -> 终端执行正式保存（建图进程必须还在运行！）
CT=ugv_jetson_ros_humble

if ! docker ps -q -f "name=^/${CT}$" | grep -q .; then
  echo "启动 Docker 容器 ${CT} ..."
  docker start "$CT"
  sleep 3
fi

gnome-terminal --title="保存地图" -- bash -lc \
  '~/ugv_ros.sh bash /home/ws/ugv_ws/save_2d_cartographer_map.sh && \
   { echo; echo "已保存到 ugv_ws/src/ugv_main/ugv_nav/maps/（map.pgm / map.yaml / map.pbstream）"; } || \
   { echo; echo "===== 保存失败：上面的 !! 行写了原因，正式地图未被改动 ====="; }; \
   echo "保存必须在建图停止之前完成；现在可以去建图窗口 Ctrl+C 退出"; \
   echo "按回车关闭本窗口"; read'
