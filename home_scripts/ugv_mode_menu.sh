#!/bin/bash
# 会话模式桌面菜单（双击「会话模式」图标打开）
# 流程：选模式 -> 释放/校验资源(7~17s 正常，预算20s) -> 自动询问是否立即启动对应实验
launch_ask() { # $1=目标模式；切换成功后调用
  case "$1" in
    ROS2)
      echo; echo "  要现在启动哪个实验？"
      echo "   1) 建图（一键建图：建图/遥控/保存 三标签页）"
      echo "   2) 纯导航（AMCL+TEB+RViz，进 RViz 先点 2D Pose Estimate 定位）"
      echo "   3) 识别+自动导航到目标（OAK 深度识别，自带导航）"
      echo "   0) 暂不"
      echo -n "   选择: "; read -r c2
      case "$c2" in
        1) ~/ugv_start_mapping.sh & ;;
        2) gnome-terminal --window --title=导航 --maximize -- bash -lc \
             '~/ugv_ros.sh ros2 launch ugv_nav nav.launch.py use_localization:=amcl use_localplan:=teb use_rviz:=true; \
              echo; echo "===== 导航已退出，按回车关闭 ====="; read' ;;
        3) echo -n "   目标颜色？1=红 2=绿 3=蓝 4=黄（默认红）: "; read -r cc
           color=$(case $cc in 2) echo green;; 3) echo blue;; 4) echo yellow;; *) echo red;; esac)
           echo "   已选 $color；运行中还可 ros2 param set /target_detector hsv_ranges 在线微调"
           gnome-terminal --window --title=识别加自动导航 --maximize -- bash -lc \
             "~/ugv_ros.sh bash /home/ws/ugv_ws/src/ugv_nav_target/scripts/run_target_nav.sh target_color:=$color; \
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
