#!/bin/bash
# 扫图自动备份（cron 每 5 分钟调用）：只在 cartographer 建图中执行，
# 崩溃/死机最多丢失 5 分钟进度。日志: ~/autosave_map.log，只保留最近 10 份。
CT=ugv_jetson_ros_humble
LOG="$HOME/autosave_map.log"
MAPS_DIR="$HOME/ugv_ws/src/ugv_main/ugv_nav/maps/autosave"

docker ps -q -f "name=^/${CT}$" | grep -q . || exit 0
docker exec "$CT" bash -lc 'source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && ros2 node list' 2>/dev/null | grep -q cartographer_node || exit 0

echo "$(date +%F_%T) autosave..." >> "$LOG"
timeout 180 docker exec "$CT" bash /home/ws/ugv_ws/autosave_map_in_container.sh >> "$LOG" 2>&1 || echo "$(date +%F_%T) FAILED" >> "$LOG"

ls -1t "$MAPS_DIR"/map_*.pbstream 2>/dev/null | tail -n +11 | xargs -r rm -f
ls -1t "$MAPS_DIR"/map_*.pgm 2>/dev/null | tail -n +11 | xargs -r rm -f
ls -1t "$MAPS_DIR"/map_*.yaml 2>/dev/null | tail -n +11 | xargs -r rm -f
