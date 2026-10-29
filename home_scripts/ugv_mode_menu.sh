#!/bin/bash
# 会话模式桌面菜单（双击「会话模式」图标打开）
# 流程：选模式 -> 释放/校验资源(7~17s 正常，预算20s) -> 自动询问是否立即启动对应实验
mem_avail_mb() { awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo; }

mem_guard() { # $1=要启动的东西；可用内存过低时拦一道（本机仅 3.5G RAM）
  local m; m=$(mem_avail_mb)
  echo "  当前可用内存: ${m}MB / 3580MB"
  if [ "$m" -lt 600 ]; then
    echo "  !! 可用内存不足 600MB，再叠 $1 极易再次冻结死机（10-27 已因此重启两次）。"
    echo -n "  仍要启动？输入 yes 才继续: "
    read -r a
    if [ "$a" != "yes" ]; then
      echo "  已取消。建议关闭 Chrome 等大内存程序，或重启后再试。"
      return 1
    fi
  fi
  return 0
}

launch_ask() { # $1=目标模式；切换成功后调用
  # 容器内 GUI(RViz/cv2窗口)需要宿主屏幕授权 root；重启后失效故每次启动 GUI 前补一次
  xhost +SI:localuser:root >/dev/null 2>&1 || true
  case "$1" in
    ROS2)
      echo; echo "  要现在启动哪个实验？"
      echo "   1) 建图（一键建图：建图/遥控/保存 三标签页，Ctrl+C自动保存）"
      echo "   2) 纯导航（载入选定地图，RViz拖2D Nav Goal，雷达绕障）"
      echo "   3) 识别+自动导航到目标（OAK 深度识别，自带导航）"
      echo "   4) 在线建图+拖拽导航（slam_nav，边走边建图，自动绕障）"
      echo "   0) 暂不"
      echo -n "   选择: "; read -r c2
      case "$c2" in
        1) mem_guard "建图栈(cartographer ~1.6G)" || return 0
           echo "   提示：扫图期间请保持 Chrome 关闭，可省数百 MB 内存。"
           ~/ugv_start_mapping.sh & ;;
        2) mem_guard "导航栈+RViz" || return 0
           echo -n "   本机开 RViz？[1=开 0=不开(推荐，省~500MB；笔记本可远程开RViz)] "
           read -r rv; RV=false; [ "$rv" = "1" ] && RV=true
           echo "   可用地图(容器路径 /home/ws/...):"
           ls ~/ugv_ws/src/ugv_main/ugv_nav/maps/*.yaml 2>/dev/null | grep -v bak | nl -w2 -s') '
           echo -n "   选地图编号(直接回车=1): "; read -r mn
           MAP=$(ls ~/ugv_ws/src/ugv_main/ugv_nav/maps/*.yaml 2>/dev/null | grep -v bak | sed -n "${mn:-1}p")
           MAPC=${MAP/#\/home\/jetson\/ugv_ws//home\/ws\/ugv_ws}
           echo "   加载地图: $MAPC (RViz=$RV)"
           gnome-terminal --window --title=导航 --maximize -- bash -lc \
             "~/ugv_ros.sh env UGV_MODEL=ugv_beast LDLIDAR_MODEL=ld19 ros2 launch ugv_nav nav.launch.py use_localization:=amcl use_localplan:=teb use_rviz:=$RV map:=$MAPC; \
              echo; echo '===== 导航已退出，按回车关闭 ====='; read" ;;
        3) mem_guard "识别+导航栈" || return 0
           echo -n "   目标颜色？1=红 2=绿 3=蓝 4=黄（默认红）: "; read -r cc
           color=$(case $cc in 2) echo green;; 3) echo blue;; 4) echo yellow;; *) echo red;; esac)
           echo "   已选 $color；运行中还可 ros2 param set /target_detector hsv_ranges 在线微调"
           gnome-terminal --window --title=识别加自动导航 --maximize -- bash -lc \
             "~/ugv_ros.sh bash /home/ws/ugv_ws/src/ugv_nav_target/scripts/run_target_nav.sh target_color:=$color; \
              echo; echo '===== 已退出，按回车关闭 ====='; read" ;;
        4) mem_guard "slam_nav+RViz" || return 0
           echo -n "   本机开 RViz？[1=开 0=不开(推荐，省~500MB)] "
           read -r rv; RV=false; [ "$rv" = "1" ] && RV=true
           echo "   在线建图+拖拽导航：RViz 里用 2D Nav Goal 拖目标，雷达见障碍自动绕（边走边建图）(RViz=$RV)"
           gnome-terminal --window --title=SLAM加拖拽导航 --maximize -- bash -lc \
             "~/ugv_ros.sh env UGV_MODEL=ugv_beast LDLIDAR_MODEL=ld19 ros2 launch ugv_nav slam_nav.launch.py use_rviz:=$RV; \
              echo; echo '===== 已退出，按回车关闭 ====='; read" ;;
      esac ;;
    OPENCV)
      echo; echo -n "  现在打开 OpenCV 颜色识别预览窗口？[1=是 0=暂不] "; read -r c2
      [ "$c2" = "1" ] && gnome-terminal --window --title=OpenCV颜色识别 -- bash -lc \
        '~/ugv_ros.sh python3 /home/ws/ugv_ws/opencv_color_lab.py; \
         echo; echo "===== 已退出，按回车关闭 ====="; read' ;;
    MANUAL)
      echo; echo -n "  现在打开键盘遥控窗口？[1=是 0=暂不] "; read -r c2
      [ "$c2" = "1" ] && ~/ugv_keyboard_teleop.sh ;;
  esac
}

while true; do
  clear
  echo "========== 会话模式管理 =========="
  ~/ugv_mode.sh status
  echo "  内存可用: $(mem_avail_mb)MB / 3580MB （低于 600MB 切勿开重栈，RViz ~500MB）"
  echo
  echo "  1) 切到 ROS2   (建图/导航/OAK深度识别)"
  echo "  2) 切到 OPENCV (USB相机 OpenCV 实验)"
  echo "  3) 切到 MANUAL (键盘遥控)"
  echo "  4) 切到 BENCH  (锁定底盘/释放相机)"
  echo "  5) 查看模式变更日志"
  echo "  0) 退出"
  echo -n "请选择: "
  read -r c
  case "$c" in
    1|2|3|4)
      mode=$(case $c in 1) echo ROS2;; 2) echo OPENCV;; 3) echo MANUAL;; 4) echo BENCH;; esac)
      if ~/ugv_mode.sh switch "$mode"; then
        [ "$mode" != "BENCH" ] && launch_ask "$mode"
      fi ;;
    5) clear; echo "===== 最近 20 条模式事件 ====="; ~/ugv_mode.sh log ;;
    0) exit 0 ;;
    *) echo "无效选择" ;;
  esac
  echo; echo "按回车继续..."
  read -r
done
