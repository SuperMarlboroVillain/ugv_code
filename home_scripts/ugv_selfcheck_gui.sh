#!/bin/bash
# 就绪自检桌面入口（双击「就绪自检」图标打开）
~/ugv_selfcheck.sh
echo
echo -n "输入 d 回车=打开诊断面板，直接回车=关闭: "
read -r c
[ "$c" = "d" ] && ~/ugv_selfcheck.sh diag
echo; echo "按回车关闭本窗口..."
read -r
