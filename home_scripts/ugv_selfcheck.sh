#!/bin/bash
# 本地实验台就绪自检（PRD FR-01）+ 本地诊断（PRD FR-13 精简版）
# 用法:
#   ugv_selfcheck.sh            就绪检查（通过/警告/失败，失败给原因+建议动作）
#   ugv_selfcheck.sh diag       诊断面板：系统/容器/节点/模式/最近事件
#   ugv_selfcheck.sh export     导出诊断包(tar.gz)，供维护者报障
set -u
CT=ugv_jetson_ros_humble
LOG="$HOME/.ugv_selfcheck.log"
PASS=0; WARN=0; FAIL=0

say() { # $1=级别(0通过/1警告/2失败) $2=检查项 $3=结果 $4=建议
  local mark; case $1 in 0) mark='[通过]';; 1) mark='[警告]';; 2) mark='[失败]';; esac
  printf '%s %-16s %s\n' "$mark" "$2" "$3"
  [ -n "${4:-}" ] && echo "         -> $4"
  echo "$(date '+%F %T') $mark $2 - $3" >> "$LOG"
  case $1 in 0) PASS=$((PASS+1));; 1) WARN=$((WARN+1));; 2) FAIL=$((FAIL+1));; esac
}

ct_ok() { docker ps -q -f "name=^/${CT}$" | grep -q .; }
ct_exec() { docker exec "$CT" bash -lc "source /opt/ros/humble/setup.bash && source /home/ws/ugv_ws/install/setup.bash && $*" 2>/dev/null; }

do_check() {
  echo "===== UGV 就绪检查 $(date '+%F %T') ====="

  # 1) 显示器
  if [ -z "${DISPLAY:-}" ]; then
    say 1 "DP显示器" "无 DISPLAY（当前为远程/无头会话）" "本地实验需接 DP 显示器；headless 时可忽略"
  elif xrandr 2>/dev/null | grep -q ' connected'; then
    local res; res=$(xrandr 2>/dev/null | grep ' connected' | head -1 | grep -oE '[0-9]+x[0-9]+' | head -1)
    say 0 "DP显示器" "已连接 ${res:-未知分辨率}"
  else
    say 2 "DP显示器" "无信号/无桌面" "先开显示器再上电 Jetson；检查 DP 线（PRD 上电时序）"
  fi

  # 2) 输入设备（键鼠；手柄可选）
  local inp; inp=$(cat /proc/bus/input/devices 2>/dev/null)
  local has_kbd has_mouse
  echo "$inp" | grep -qiE '^N.*(keyboard|kbd)' && has_kbd=1 || has_kbd=0
  echo "$inp" | grep -qiE '^N.*(mouse|trackball)' && has_mouse=1 || has_mouse=0
  if [ $has_kbd -eq 1 ] && [ $has_mouse -eq 1 ]; then
    say 0 "键鼠" "键盘+鼠标均已识别"
  elif [ $has_kbd -eq 1 ] || [ $has_mouse -eq 1 ]; then
    say 1 "键鼠" "只识别到 $([ $has_kbd -eq 1 ] && echo 键盘 || echo 鼠标)" "需要完整遥控体验时检查另一个 USB 口；不阻断实验"
  else
    say 1 "键鼠" "均未识别" "允许继续（2026-10-27 按使用者要求降级为警告）：MANUAL 遥控不可用，ROS2/OPENCV 模式不受影响"
  fi

  # 3) 磁盘 / 4) 内存
  local avail_mb; avail_mb=$(df -m --output=avail "$HOME" | tail -1 | tr -d ' ')
  if   [ "$avail_mb" -lt 500 ]; then say 2 "磁盘余量" "${avail_mb}MB" "先清理旧数据包，磁盘满会让建图/记录直接失败"
  elif [ "$avail_mb" -lt 2048 ]; then say 1 "磁盘余量" "${avail_mb}MB" "建图+数据包建议预留 2GB 以上"
  else say 0 "磁盘余量" "${avail_mb}MB"; fi
  local mem_mb; mem_mb=$(free -m | awk '/^Mem:/{print $7}')
  if [ "$mem_mb" -lt 800 ]; then say 1 "内存余量" "可用 ${mem_mb}MB" "扫图前关掉 Chrome 等大程序（3.5G 内存，溢出会被 earlyoom 杀进程）"
  else say 0 "内存余量" "可用 ${mem_mb}MB"; fi

  # 5) Docker 容器 / 6) 工作空间
  if ct_ok; then
    say 0 "ROS2容器" "$CT 运行中"
  elif docker ps -aq -f "name=^/${CT}$" | grep -q .; then
    say 2 "ROS2容器" "容器存在但未运行" "执行: docker start $CT"
  else
    say 2 "ROS2容器" "容器不存在" "检查 Docker 与工作空间 /home/ws/ugv_ws"
  fi
  if ct_ok; then
    local pkgs; pkgs=$(ct_exec 'ros2 pkg list' | grep -cE '^ugv_(bringup|nav|slam|vision|auto|nav_target)$')
    [ "$pkgs" -ge 6 ] && say 0 "工作空间" "关键功能包齐全($pkgs/6)" || say 2 "工作空间" "功能包缺失(只匹配$pkgs/6)" "进容器 colcon build（--symlink-install），看报错"
  fi

  # 7~9) 四路 USB 按口位核对
  local usb; usb=$(lsusb)
  echo "$usb" | grep -q '03e7:2485' && say 0 "OAK-D Lite" "已枚举(03e7:2485)" || say 2 "OAK-D Lite" "未枚举" "检查 OAK 的 USB 口与供电（深度通路必需）"
  if echo "$usb" | grep -q '0abd:8050' && [ -e /dev/video0 ]; then
    say 0 "USB广角相机" "已枚举(0abd:8050, /dev/video0)"
  else
    say 2 "USB广角相机" "未枚举" "检查相机 USB 口（OpenCV 通路必需）"
  fi
  echo "$usb" | grep -q '1a86:' && say 0 "激光雷达" "已枚举(CH34x串口)" || say 2 "激光雷达" "未枚举" "检查雷达 USB 口与供电"

  # 10) 下位机串口
  local ser=""
  [ -e /dev/ttyACM0 ] && ser="/dev/ttyACM0"
  for d in /dev/ttyUSB*; do [ -e "$d" ] && ser="$ser $d"; done
  ser=$(echo "$ser" | sed 's/^ //')
  if [ -n "$ser" ]; then
    if ct_ok && docker exec "$CT" bash -c "ls $ser >/dev/null 2>&1"; then
      say 0 "下位机串口" "$ser 容器内可见"
    else
      say 2 "下位机串口" "容器内不可见" "检查容器设备映射；重启容器"
    fi
  else
    say 2 "下位机串口" "不存在" "检查 ESP32/雷达 USB；插错口位按 PRD 口位提示重插"
  fi

  # 11) 相机占用者（资源争用可见性）
  local pids; pids=$(fuser /dev/video0 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)
  if [ -n "$pids" ]; then
    local who; who=$(ps -o comm= -p $(echo "$pids" | tr '\n' ',' | sed 's/,$//') 2>/dev/null | sort -u | tr '\n' ' ')
    say 1 "相机占用者" "$who" "进 OPENCV 模式前执行: ~/ugv_factory.sh stop"
  elif pgrep -f 'ugv_jetson/app\.py' >/dev/null 2>&1; then
    say 1 "相机占用者" "出厂 Web 主程序(未持句柄但在跑)" "建议: ~/ugv_factory.sh disable"
  else
    say 0 "相机占用者" "无，相机空闲"
  fi

  # 12) 地图可用性
  local maps=~/ugv_ws/src/ugv_main/ugv_nav/maps
  if [ -s "$maps/map.pgm" ] && [ -f "$maps/map.yaml" ]; then
    say 0 "默认地图" "map.pgm $(stat -c%s "$maps/map.pgm")字节 + yaml"
  else
    say 1 "默认地图" "缺失或为空" "先跑「一键建图」并保存（导航前必需）"
  fi

  # 13) 内存保护
  if systemctl is-active earlyoom >/dev/null 2>&1; then
    say 0 "内存保护" "earlyoom 运行中"
  else
    say 1 "内存保护" "earlyoom 未运行" "内存耗尽会整机卡死；执行: sudo systemctl enable --now earlyoom"
  fi

  echo "=================================="
  echo "通过 $PASS  警告 $WARN  失败 $FAIL"
  [ $FAIL -gt 0 ] && { echo "存在失败项：修复后再进入实验模式（或先切 BENCH 排查）"; exit 1; }
  echo "就绪检查通过，可进入实验流程"
}

do_diag() {
  echo "===== 诊断面板 $(date '+%F %T') ====="
  echo "--- 系统 ---"
  uptime; free -h | head -2
  local t temp
  for t in /sys/devices/virtual/thermal/thermal_zone*/temp; do
    [ -r "$t" ] || continue
    temp=$(cat "$t" 2>/dev/null) || continue
    [ -n "$temp" ] && printf '温度 %-4s %.1f°C\n' "$(basename $(dirname $t) | sed 's/thermal_zone//')" "$((temp/1000))"
  done | head -6
  df -h "$HOME" | tail -1
  echo "--- 出厂程序 ---"; "$HOME/ugv_factory.sh" status
  echo "--- 会话模式 ---"; "$HOME/ugv_mode.sh" status
  echo "--- 最近模式事件 ---"; tail -10 "$HOME/.ugv_mode.log" 2>/dev/null || echo "  无"
  echo "--- 自动备份日志 ---"; tail -3 "$HOME/autosave_map.log" 2>/dev/null || echo "  无"
  echo "--- 电池/电压 ---"; echo "  需 ESP32 回报（PRD FR-13，接 JSON 指令集后补）"
}

do_export() {
  local out="$HOME/ugv_diagpack_$(date +%Y%m%d_%H%M%S).tar.gz"
  local tmp; tmp=$(mktemp -d)
  crontab -l > "$tmp/crontab.txt" 2>/dev/null
  { free -h; df -h; uname -a; docker ps -a; } > "$tmp/system.txt" 2>/dev/null
  cp "$HOME/.ugv_mode.log" "$HOME/.ugv_selfcheck.log" "$HOME/autosave_map.log" "$HOME/ugv.log" "$tmp/" 2>/dev/null
  tar -czf "$out" -C "$tmp" . 2>/dev/null
  rm -rf "$tmp"
  echo "诊断包已导出: $out"
}

case "${1:-check}" in
  check|"")  do_check ;;
  diag)      do_diag ;;
  export)    do_export ;;
  *) echo "用法: $0 [check|diag|export]" >&2; exit 2 ;;
esac
