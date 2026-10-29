#!/bin/bash
# 在 docker 容器内执行：保存 pbstream 并转换为 pgm+yaml（不依赖 /map 话题，负载高也不超时）
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash
TS=$(date +%Y%m%d_%H%M%S)
DIR=/home/ws/ugv_ws/src/ugv_main/ugv_nav/maps/autosave
mkdir -p "$DIR"
ros2 service call /write_state cartographer_ros_msgs/srv/WriteState \
  "{filename: '$DIR/map_$TS.pbstream', include_unfinished_submaps: true}" && \
ros2 run cartographer_ros cartographer_pbstream_to_ros_map \
  -map_filestem="$DIR/map_$TS" \
  -pbstream_filename="$DIR/map_$TS.pbstream" \
  -resolution=0.05 || exit 1
# 空图（建图刚开始）不落盘，避免 0 字节文件占用备份名额
PGM_SIZE=$(stat -c%s "$DIR/map_$TS.pgm" 2>/dev/null || echo 0)
if [ "$PGM_SIZE" -lt 2000 ]; then
  echo "autosave: map too small (${PGM_SIZE}B), discarding"
  rm -f "$DIR/map_$TS.pbstream" "$DIR/map_$TS.pgm" "$DIR/map_$TS.yaml"
  exit 1
fi
