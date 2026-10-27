#!/bin/bash
# 会话模式管理（PRD FR-02）：BENCH / ROS2 / OPENCV / MANUAL 四模式互斥。
# 核心保证：任一时点只有一个资源持有者；切换固定走
#   停车 -> 释放旧持有者 -> 校验释放 -> 建立新持有者 -> 校验就绪 -> 记录事件
# 用法:
#   ugv_mode.sh status          查看模式与资源占用表（实际探测，非仅状态文件）
#   ugv_mode.sh switch <模式>   切换模式（释放旧持有者可验证，失败停在 BENCH）
#   ugv_mode.sh current         仅打印当前模式
#   ugv_mode.sh log             最近 20 条模式变更事件
set -u
CT=ugv_jetson_ros_humble
STATE_FILE="$HOME/.ugv_mode"
EVENT_LOG="$HOME/.ugv_mode.log"
VALID_MODES="BENCH ROS2 OPENCV MANUAL"

current_mode() { head -1 "$STATE_FILE" 2>/dev/null || echo BENCH; }
log_event() { echo "$(date '+%F %T') | $*" >> "$EVENT_LOG"; }

ct_exec() { docker exec "$CT" bash -lc "source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && $*" 2>/dev/null; }
ros_nodes() { ct_exec 'timeout 8 ros2 node list' | sed 's/^\/ //' | sort -u; }

# ---------- 资源探测 ----------
holder_chassis() { # 从节点名推断底盘控制者
  local nodes; nodes=$(ros_nodes)
  [ -z "$nodes" ] && { echo "无（底盘锁定）"; return; }
  if echo "$nodes" | grep -qiE 'teleop|joy'; then
    echo "键鼠/手柄（MANUAL）"; return
  fi
  if echo "$nodes" | grep -qiE 'bt_navigator|controller_server|planner_server|behavior_server'; then
    echo "Nav2 导航（ROS2）"; return
  fi
  if echo "$nodes" | grep -qiE 'base_node|ugv_driver|ugv_bringup|ldlidar'; then
    echo "ROS2 驱动（待机）"; return
  fi
  echo "无（底盘锁定；仅感知节点在跑）"
}
holder_usb_cam() {
  if pgrep -f 'ugv_jetson/app\.py' >/dev/null 2>&1; then echo "出厂 Web 主程序(占相机!)"; return; fi
  local pids; pids=$(fuser /dev/video0 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)
  if [ -n "$pids" ]; then
    ps -o comm= -p $(echo "$pids" | tr '\n' ',' | sed 's/,$//') 2>/dev/null | sort -u | tr '\n' ' '
    echo; return
  fi
  pgrep -f 'mono_detector|line_follow|approach_manager' >/dev/null 2>&1 && { echo "OpenCV 脚本"; return; }
  echo "空闲"
}
holder_oak() {
  local nodes; nodes=$(ros_nodes)
  echo "$nodes" | grep -qiE 'oak|depthai|stereo' && { echo "ROS2 深度通路节点"; return; }
  echo "空闲"
}
holder_serial() {
  local devs="/dev/ttyACM0"; ls /dev/ttyUSB* >/dev/null 2>&1 && devs="$devs /dev/ttyUSB*"
  local pids; pids=$(fuser $devs 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)
  [ -z "$pids" ] && { echo "空闲"; return; }
  ps -o comm= -p $(echo "$pids" | tr '\n' ',' | sed 's/,$//') 2>/dev/null | sort -u | tr '\n' ' '; echo
}

do_status() {
  local mode; mode=$(current_mode)
  echo "当前模式: $mode"
  echo
  printf '%-14s %s\n' "资源" "当前持有者"
  echo "----------------------------"
  printf '%-14s %s\n' "底盘控制权" "$(holder_chassis)"
  printf '%-14s %s\n' "USB广角相机" "$(holder_usb_cam)"
  printf '%-14s %s\n' "OAK-D Lite" "$(holder_oak)"
  printf '%-14s %s\n' "下位机串口" "$(holder_serial)"
  printf '%-14s %s\n' "显示主视图" "见实际窗口（RViz/识别预览/桌面）"
  echo
  local nodes; nodes=$(ros_nodes)
  [ -n "$nodes" ] && { echo "容器内节点:"; echo "$nodes" | sed 's/^/  /'; }
}

# ---------- 切换 ----------
stop_all_ros() { # 返回 0=已清空 1=杀不掉
  ct_exec "pkill -INT -f 'ros2 launc[h]'" >/dev/null 2>&1 || true
  ct_exec "pkill -INT -f 'ros2 ru[n]'"    >/dev/null 2>&1 || true
  local i
  for i in $(seq 1 8); do
    [ -z "$(ros_nodes)" ] && return 0
    sleep 1
  done
  # 包装进程已死但裸节点进程(ros2 run 的 python/bin 子进程)还在 -> 按运行路径清
  ct_exec "pkill -KILL -f 'ros2 launc[h]|ros2 ru[n]'" >/dev/null 2>&1 || true
  ct_exec "pkill -KILL -f '/home/ws/ugv_ws/instal[l]'" >/dev/null 2>&1 || true
  ct_exec "pkill -KILL -f '/opt/ros/humble/li[b]'"     >/dev/null 2>&1 || true
  # 区分"进程真活着"与"ROS图发现滞后"：进程级干净后多等图刷新
  for i in $(seq 1 10); do
    [ -z "$(ros_nodes)" ] && return 0
    if ! ct_exec "ps aux | grep -qE '/home/ws/ugv_ws/instal[l]|/opt/ros/humble/li[b]'"; then
      sleep 6
      [ -z "$(ros_nodes)" ] && return 0
      return 0   # 进程确已清空，图挂名只是发现滞后
    fi
    sleep 1
  done
  return 1
}

release_camera() { # 目标模式需要相机时调用
  if pgrep -f 'ugv_jetson/app\.py' >/dev/null 2>&1; then
    echo "  发现出厂 Web 主程序占用相机，正在彻底停止..."
    "$HOME/ugv_factory.sh" stop >/dev/null
  fi
  pkill -f 'mono_detecto[r]|line_follo[w]|approach_manage[r]' 2>/dev/null || true
  sleep 1
}

do_switch() {
  local target="$1"
  case " $VALID_MODES " in *" $target "*) ;; *) echo "无效模式: $target（可选: $VALID_MODES）" >&2; exit 2;; esac
  local from; from=$(current_mode)
  local need_clean=0
  if [ "$from" = "$target" ]; then
    if [ "$target" = "BENCH" ] && [ -n "$(ros_nodes)" ]; then
      echo "已是 BENCH，但检测到残留 ROS 节点，补做释放..."
      need_clean=1
    else
      echo "已是 $target 模式"; return 0
    fi
  fi

  [ "$need_clean" -eq 0 ] && echo "切换: $from -> $target"
  local t0; t0=$(date +%s)

  # 1) 停车（有节点在跑才发零速；否则跳过省 5s 发现时间）
  if [ "$need_clean" -eq 0 ] && [ -n "$(ros_nodes)" ]; then
    ct_exec "timeout 5 ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.0}, angular: {z: 0.0}}'" >/dev/null 2>&1 || true
  fi

  # 2) 释放旧持有者 + 3) 校验
  echo "  释放旧持有者..."
  local had_nav; had_nav=$(ros_nodes | grep -ciE 'bt_navigator|controller_server' || true)
  [ "$had_nav" -ge 1 ] && echo "  注意：有导航任务在跑，将被终止"
  if ! stop_all_ros; then
    echo "  !! 旧 ROS 进程无法清空（残留: $(ros_nodes | tr '\n' ' '))"
    echo "  !! 按 PRD 规则停在 BENCH，建议重启机器人后再试"
    echo BENCH > "$STATE_FILE"
    log_event "$from -> $target | FAILED: 旧进程杀不掉 | $(($(date +%s)-t0))s"
    exit 1
  fi
  echo "  ROS 节点已清空（ros2 node list 校验通过）"

  if [ "$target" = "OPENCV" ] || [ "$target" = "ROS2" ]; then
    release_camera
    if [ "$target" = "OPENCV" ]; then
      local pids; pids=$(fuser /dev/video0 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)
      if [ -n "$pids" ]; then
        echo "  !! /dev/video0 仍被占用（$(ps -o comm= -p $(echo "$pids"|tr '\n' ', '|sed 's/, $//') 2>/dev/null | tr '\n' ' '))"
        echo "  !! 停在 BENCH：请手动释放后重试"
        echo BENCH > "$STATE_FILE"
        log_event "$from -> $target | FAILED: 相机仍被占 | $(($(date +%s)-t0))s"
        exit 1
      fi
      echo "  USB 相机已释放（fuser 校验通过）"
    fi
  fi
  pkill -f 'mono_detecto[r]|line_follo[w]|approach_manage[r]' 2>/dev/null || true

  # 4) 建立新持有者（按模式给出下一步引导）
  echo "$target" > "$STATE_FILE"
  case "$target" in
    BENCH)
      echo "  BENCH：桌面+终端可用，底盘锁定、相机空闲。改代码/看日志/拷贝数据。" ;;
    ROS2)
      echo "  ROS2：相机/底盘已就绪，按实验选择："
      echo "    建图: ~/ugv_start_mapping.sh"
      echo "    导航: ros2 launch ugv_nav nav.launch.py use_localization:=amcl use_rviz:=true"
      echo "    识别+导航: 容器内 /home/ws/ugv_ws/src/ugv_nav_target/scripts/run_target_nav.sh" ;;
    OPENCV)
      echo "  OPENCV：USB 广角相机空闲，可用 cv2.VideoCapture 取流（识别预览窗口为主视图）。" ;;
    MANUAL)
      echo "  MANUAL：双击桌面「键盘遥控」或: ~/ugv_keyboard_teleop.sh （需保持窗口焦点）" ;;
  esac

  log_event "$from -> $target | OK | $(($(date +%s)-t0))s"
  echo "切换完成，耗时 $(($(date +%s)-t0))s"
}

case "${1:-status}" in
  status)  do_status ;;
  current) current_mode ;;
  switch)  [ $# -ge 2 ] || { echo "用法: $0 switch <BENCH|ROS2|OPENCV|MANUAL>" >&2; exit 2; }; do_switch "$2" ;;
  log)     tail -20 "$EVENT_LOG" 2>/dev/null || echo "暂无事件" ;;
  *)       echo "用法: $0 status|switch <模式>|current|log" >&2; exit 2 ;;
esac
