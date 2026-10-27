#!/bin/bash
# 出厂程序管理桌面菜单（双击「出厂程序管理」图标打开）
# app.py=出厂Web主程序(占相机)  JupyterLab=出厂笔记本(吃内存)
# 做 ROS2/OpenCV 实验前建议：先 3) 彻底停止并禁用自启
while true; do
  clear
  echo "========== 出厂常驻程序管理 =========="
  ~/ugv_factory.sh status
  echo
  echo "  1) 仅停止进程（本次有效，重启后会自启）"
  echo "  2) 恢复开机自启（并启动 jupyter）"
  echo "  3) 彻底停止并禁用自启（实验前推荐）"
  echo "  4) 立即启动 Web 主程序"
  echo "  0) 退出"
  echo -n "请选择: "
  read -r c
  case "$c" in
    1) ~/ugv_factory.sh stop ;;
    2) ~/ugv_factory.sh restore ;;
    3) ~/ugv_factory.sh disable ;;
    4) ~/ugv_factory.sh start ;;
    0) exit 0 ;;
    *) echo "无效选择" ;;
  esac
  echo; echo "按回车继续..."
  read -r
done
