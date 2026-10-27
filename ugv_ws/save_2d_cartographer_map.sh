#!/bin/bash
# 在容器内执行：先存 cartographer 状态(pbstream)，再从 pbstream 生成 pgm+yaml。
# 不依赖 /map 话题订阅（map_saver 默认只等 2s，扫图负载高时易超时失败）。
# 2026-10-27 加固：写临时文件 + 校验非空才原子替换正式地图，并保留旧图备份。
#   背景：10-23 建图仅 1 分钟时执行保存，finished 子图为 0，pbstream_to_ros_map
#   生成 0 字节 pgm 直接冲掉了可用地图。现 WriteState 带 include_unfinished_submaps
#   （覆盖当前未完成的子图，与 /map 显示一致），且空图不再落盘。
# 注意：先 source 再 set -u（ROS setup 脚本在 set -u 下会触发 unbound variable 退出）
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash
set -u

DIR=/home/ws/ugv_ws/src/ugv_main/ugv_nav/maps
cd "$DIR" || exit 1
TS=$(date +%Y%m%d_%H%M%S)
TMP="map_saving_$TS"

if ! ros2 service list 2>/dev/null | grep -q '^/write_state'; then
  echo "!! /write_state 服务不存在：cartographer 没在运行（建图没启动或已退出）。"
  echo "!! 正式地图未被改动。"
  exit 1
fi

ros2 service call /write_state cartographer_ros_msgs/srv/WriteState \
  "{filename: '$DIR/$TMP.pbstream', include_unfinished_submaps: true}" || {
  echo "!! 写状态失败：cartographer 服务调用出错。"
  rm -f "$TMP.pbstream"; exit 1; }

ros2 run cartographer_ros cartographer_pbstream_to_ros_map \
  -map_filestem="$DIR/$TMP" \
  -pbstream_filename="$DIR/$TMP.pbstream" \
  -resolution=0.05 || { echo "!! pbstream 转地图失败"; exit 1; }

PGM_SIZE=$(stat -c%s "$TMP.pgm" 2>/dev/null || echo 0)
if [ "$PGM_SIZE" -lt 2000 ] || [ ! -f "$TMP.yaml" ]; then
  echo "!! 生成的地图为空或过小（${PGM_SIZE} 字节）、或缺少 yaml。"
  echo "!! 常见原因：建图刚开始、子图无内容。正式地图未被改动，请继续扫图后再保存。"
  rm -f "$TMP.pgm" "$TMP.yaml" "$TMP.pbstream"; exit 1
fi

# 旧图备份（保留最近 5 份），再原子替换
if [ -s map.pgm ]; then
  cp -a map.pgm "map.pgm.bak_$TS"; cp -a map.yaml "map.yaml.bak_$TS"
  ls -1t map.pgm.bak_* 2>/dev/null | tail -n +6 | xargs -r rm -f
  ls -1t map.yaml.bak_* 2>/dev/null | tail -n +6 | xargs -r rm -f
fi
mv "$TMP.pgm" map.pgm; mv "$TMP.yaml" map.yaml; mv "$TMP.pbstream" map.pbstream
echo "已保存: $DIR/map.pgm / map.yaml / map.pbstream（pgm ${PGM_SIZE} 字节）"
