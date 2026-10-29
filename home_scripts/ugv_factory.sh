#!/bin/bash
# 出厂常驻程序管理（PRD FR-02 规则 4）：彻底停止 / 禁用自启 / 恢复自启 / 状态
#   app.py    : 出厂 Flask Web 主程序(5000端口)，常驻占用 USB 相机，crontab 开机自启
#   jupyter   : JupyterLab(8888端口)，常驻吃内存
# 本地直连(DP)模式下两者均非必需，相机必须留给 ROS2/OPENCV 实验。
# 用法: ugv_factory.sh status|stop|disable|restore|start
set -u
APP_PATTERN='ugv_jetson/app\.py'

app_running() { pgrep -f "$APP_PATTERN" >/dev/null 2>&1; }
jupyter_running() { pgrep -f 'jupyter-lab' >/dev/null 2>&1; }
cron_app_line() { crontab -l 2>/dev/null | grep 'ugv_jetson/app.py'; }
cron_enabled() { crontab -l 2>/dev/null | grep -q '^[^#]*ugv_jetson/app.py'; }
JUP_SVC=ugv_jupyter.service
jup_active() { systemctl is-active "$JUP_SVC" >/dev/null 2>&1; }
jup_enabled() { systemctl is-enabled "$JUP_SVC" >/dev/null 2>&1; }

stop_one() { # $1=进程匹配 $2=显示名。括号技巧防 pkill 误杀调用方 shell
  local pat="${1%?}[${1: -1}]"
  pgrep -f "$pat" >/dev/null 2>&1 || { echo "  $2：未在运行"; return 0; }
  pkill -INT -f "$pat" 2>/dev/null; sleep 2
  if pgrep -f "$pat" >/dev/null 2>&1; then
    pkill -KILL -f "$pat" 2>/dev/null; sleep 1
  fi
  if pgrep -f "$pat" >/dev/null 2>&1; then echo "  $2：!! 无法终止"; return 1; fi
  echo "  $2：已停止"
}

stop_jupyter() { # jupyter 由 systemd 托管(Restart=always)，进程级 kill 会被拉起
  if sudo -n systemctl stop "$JUP_SVC" >/dev/null 2>&1; then
    echo "  JupyterLab：已通过 systemctl 停止"; return 0
  fi
  stop_one 'jupyter-lab' "JupyterLab(进程级,临时)"
  if jup_active; then
    echo "  !! $JUP_SVC 是 systemd 服务(Restart=always)，进程还会被拉起。"
    echo "  !! 彻底停止需手动执行: sudo systemctl disable --now $JUP_SVC"
  fi
}

cron_disable() {
  local tmp; tmp=$(mktemp)
  crontab -l 2>/dev/null | awk '
    /ugv_jetson\/app\.py/ {
      if ($0 ~ /^#/) { print; next }            # 已注释则原样保留
      print "#[factory-disabled] " $0; next
    } { print }' > "$tmp"
  crontab "$tmp"; rm -f "$tmp"
}

cron_enable() {
  local tmp; tmp=$(mktemp)
  crontab -l 2>/dev/null | sed 's|^#\[factory-disabled\] *||' | awk '
    /ugv_jetson\/app\.py/ {
      if ($0 ~ /^#@reboot/) { sub(/^#/, ""); print; next }
      print; next
    } { print }' > "$tmp"
  crontab "$tmp"; rm -f "$tmp"
}

case "${1:-status}" in
  status)
    echo "== 出厂常驻程序状态 =="
    if app_running; then echo "  Web主程序 app.py ：运行中（占用相机！）"; else echo "  Web主程序 app.py ：未运行"; fi
    if jup_active; then echo "  JupyterLab(8888) ：运行中(systemd $JUP_SVC)"; else echo "  JupyterLab(8888) ：未运行"; fi
    if cron_enabled; then echo "  app.py 开机自启  ：已启用（crontab）"; else echo "  app.py 开机自启  ：已禁用"; fi
    if jup_enabled; then echo "  jupyter 开机自启 ：已启用（systemd）"; else echo "  jupyter 开机自启 ：已禁用"; fi
    ;;
  stop)
    echo "== 停止出厂常驻程序 =="
    stop_one "$APP_PATTERN" "Web主程序 app.py"
    stop_jupyter
    ;;
  disable)
    echo "== 彻底停止并禁用自启 =="
    stop_one "$APP_PATTERN" "Web主程序 app.py"
    stop_jupyter
    cron_disable
    cron_enabled && echo "  app.py 自启：禁用失败?!" || echo "  app.py 自启：已禁用（crontab 行已注释）"
    if sudo -n systemctl disable "$JUP_SVC" >/dev/null 2>&1; then
      echo "  jupyter 自启：已禁用（systemd）"
    else
      echo "  jupyter 自启：无法自动禁用（需密码）。手动执行: sudo systemctl disable --now $JUP_SVC"
    fi
    ;;
  restore)
    echo "== 恢复开机自启（并立即启动）=="
    cron_enable
    cron_enabled && echo "  app.py 自启：已启用" || echo "  app.py 自启：仍禁用?"
    if sudo -n systemctl enable --now "$JUP_SVC" >/dev/null 2>&1; then
      echo "  jupyter 自启：已启用并已启动"
    else
      echo "  jupyter 自启：无法自动恢复（需密码）。手动执行: sudo systemctl enable --now $JUP_SVC"
    fi
    echo "  提示：app.py 想立即启动用: $0 start"
    ;;
  start)
    echo "== 立即启动出厂 Web 主程序 =="
    app_running && { echo "  已在运行"; exit 0; }
    nohup "$HOME/ugv_jetson/ugv-env/bin/python" "$HOME/ugv_jetson/app.py" >> "$HOME/ugv.log" 2>&1 &
    sleep 2; app_running && echo "  已启动(5000端口)，日志 ~/ugv.log" || echo "  !! 启动失败，看 ~/ugv.log"
    ;;
  *) echo "用法: $0 status|stop|disable|restore|start" >&2; exit 2 ;;
esac
