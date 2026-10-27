#!/bin/bash
# 建图会话包装（容器内运行；PRD FR-05：结束建图必须保存，禁止静默丢弃）
# 用法: bash /home/ws/ugv_ws/mapping_autosave_wrap.sh [save名称] [launch参数...]
#   本窗口按 Ctrl+C = 先自动保存地图(名称默认map) -> 再停止建图；
#   保存失败会明确报警（可用 maps/autosave/ 最近 .pbstream 断点续扫），不静默。
# 原理: 建图进程用 setsid 放独立会话，Ctrl+C 只到本包装层，趁 cartographer
#   还活着完成 write_state 保存，然后再停建图。
# 注意: 非交互 bash 对 & 后台子进程默认忽略 SIGINT（disposition 会过 exec 继承），
#   所以停建图用 TERM->KILL 升级链，不能指望 SIGINT。
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash
set -u

SAVE_NAME=${1:-map}; shift || true
PIDFILE=/tmp/mapping_launch_$$.pid
rm -f "$PIDFILE"

STACK_PATTERN='cartographer_nod[e]|cartographer_occupancy|ugv_drive[r]|base_nod[e]|ldlida[r]|rf2o_laser_odometr[y]|joy_nod[e]|joy_teleo[p]|cmd_vel_watchdo[g]|robot_state_publisher|joint_state_publisher'

stop_stack() { # INT 进程组(ros2 launch 优雅带退子节点) -> KILL -> 模式清扫防孤儿
  kill -INT -- -"$LPID" 2>/dev/null
  local _
  for _ in 1 2 3 4 5 6 7 8; do
    kill -0 "$LPID" 2>/dev/null || break
    sleep 1
  done
  kill -KILL -- -"$LPID" 2>/dev/null
  pkill -KILL -f "$STACK_PATTERN" 2>/dev/null
}

# setsid 会话里先 trap - INT 把 SIGINT 恢复默认（清除 bash 后台进程忽略 SIGINT 的继承），
# 这样 ros2 launch 的 python 才能装上 SIGINT handler，收到 -INT 时优雅带退全部子节点。
setsid bash -c "trap - INT QUIT; echo \$\$ > '$PIDFILE'; exec ros2 launch ugv_auto stage1_mapping_joy.launch.py $*" &
sleep 2
LPID=$(cat "$PIDFILE" 2>/dev/null || true)
[ -z "$LPID" ] && { echo "!! 建图进程启动失败"; exit 1; }
echo "建图已启动(pid $LPID)。扫完后在本窗口按 Ctrl+C：将先自动保存地图[$SAVE_NAME]再停止（约 5~15 秒）。"
echo "（保存名称可改: mapping_autosave_wrap.sh 名称 load_state:=...）"

SAVED=-1   # -1 未触发 1 成功 0 失败
do_save() {
  [ "$SAVED" -ne -1 ] && return
  echo; echo "===== 停止指令收到：正在自动保存地图 [$SAVE_NAME] ====="
  if bash /home/ws/ugv_ws/save_2d_cartographer_map.sh "$SAVE_NAME"; then
    SAVED=1
    echo "===== 自动保存成功：ugv_nav/maps/$SAVE_NAME.pgm/.yaml/.pbstream ====="
  else
    SAVED=0
    echo "===== !! 自动保存失败（cartographer 可能已先退出；可用 maps/autosave/ 最近 .pbstream 断点续扫）====="
  fi
  stop_stack
}
trap do_save INT TERM

wait "$LPID" 2>/dev/null
RC=$?
trap - INT TERM

# launch 自行退出(非Ctrl+C)的兜底：服务还在就补一次保存
if [ "$SAVED" -eq -1 ]; then
  echo; echo "===== 建图进程已退出(rc=$RC)，尝试兜底保存 ====="
  if bash /home/ws/ugv_ws/save_2d_cartographer_map.sh "$SAVE_NAME"; then
    SAVED=1; echo "===== 兜底保存成功 ====="
  else
    SAVED=0
  fi
  stop_stack
fi
if [ "$SAVED" -eq 0 ]; then
  echo; echo "!! 本次地图未保存成功。5分钟级自动备份见 maps/autosave/（最新 .pbstream 可 load_state 续扫）"
fi
echo "（建图会话结束，地图已保存到 [$SAVE_NAME]）"
exit 0
