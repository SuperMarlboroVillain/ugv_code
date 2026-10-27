#!/bin/bash
# UGV 一键建图 v2（2026-10-27）：扫完在建图标签页按 Ctrl+C，
#   自动保存地图 -> 停止建图 -> 键盘遥控标签页自动退出（PRD FR-05 禁止静默丢弃）
# 断点续扫: ~/ugv_start_mapping.sh load_state:=/home/ws/ugv_ws/src/ugv_main/ugv_nav/maps/autosave/xxx.pbstream
# 保存命名: ~/ugv_start_mapping.sh save:=实验二 load_state:=...   （地图名默认 map）
CT=ugv_jetson_ros_humble
SAVE_NAME=map
ARGS=""
for a in "$@"; do
  case "$a" in
    save:=*) SAVE_NAME="${a#save:=}" ;;
    *) ARGS="$ARGS $a" ;;
  esac
done

if ! docker ps -q -f "name=^/${CT}$" | grep -q .; then
  echo "启动 Docker 容器 ${CT} ..."
  docker start "$CT"
  sleep 3
fi

# 互斥守卫（FR-02）：已有一个建图/导航会话在跑时拒绝叠加，防止多 cartographer 抢雷达
if docker exec "$CT" bash -lc 'source /opt/ros/humble/setup.bash 2>/dev/null && ros2 node list' 2>/dev/null | grep -q cartographer_node; then
  echo "!! 已有一个建图会话在运行（cartographer_node 已存在）。"
  echo "!! 请先结束那个会话（在其窗口 Ctrl+C），或先用 会话模式 图标切到 BENCH 再重试。"
  echo "!! 拒绝叠加第二个建图实例（多实例会互相污染地图并抢占雷达）。"
  exit 1
fi

# 内存提醒（本机仅 3.5G RAM；2026-10-27 曾因内存冻结重启两次）：不拦截，只提醒
AVAIL=$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo)
echo "当前可用内存: ${AVAIL}MB / 3580MB"
[ "$AVAIL" -lt 500 ] && echo "!! 内存偏紧：cartographer(~1.6G)+桌面，冻结风险高。强烈建议关掉 Chrome 再扫。"
pgrep -x chrome >/dev/null 2>&1 && echo "提示：检测到 Chrome 在运行，扫图期间建议关闭（可省数百 MB）。"

gnome-terminal --window --title="一键建图(扫完Ctrl+C自动保存)" --maximize -- bash -lc \
  "~/ugv_ros.sh bash /home/ws/ugv_ws/mapping_autosave_wrap.sh $SAVE_NAME $ARGS; \
   echo; \
   if [ -s ~/ugv_ws/src/ugv_main/ugv_nav/maps/$SAVE_NAME.pgm ]; then \
     echo \"===== 地图已保存: ugv_nav/maps/$SAVE_NAME.pgm/.yaml/.pbstream =====\"; \
   else \
     echo '===== !! 保存未成功，看上面 !! 行；autosave/ 里有5分钟级备份 ====='; \
   fi; \
   echo '按回车关闭本窗口'; read" \
  --tab --title="键盘遥控" -- bash -lc \
  '~/ugv_ros.sh bash /home/ws/ugv_ws/teleop_watchdog_wrap.sh; \
   echo; echo "===== 遥控已退出 ====="; read'
