#!/bin/bash
# 第一步：2D 激光 SLAM 建图（gmapping + RViz + 键盘遥控），退出时自动询问保存地图
# 用法：在 Docker 容器终端中执行本脚本
set -u
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash 2>/dev/null

echo "=============================================="
echo " 1) 启动 gmapping 建图节点与 RViz ..."
echo " 2) 然后就可以用键盘控制小车扫描建图："
echo "      w/s 前进后退   a/d 左右转向   空格 急停"
echo "      （速度加减按 ugv_tools 的提示）"
echo " 3) 建图完成后按 Ctrl+C 退出键盘控制，"
echo "    本脚本会询问是否保存地图。"
echo "=============================================="

# 让建图进程忽略 Ctrl+C（保存地图时它必须保持运行）
(trap '' INT; exec ros2 launch ugv_slam gmapping.launch.py use_rviz:=true) &
SLAM_PID=$!
sleep 6

# Ctrl+C 只退出键盘控制，脚本继续走保存流程
trap 'echo; echo "键盘控制已退出。"' INT
ros2 run ugv_tools keyboard_ctrl

echo "是否保存地图？[Y/n]（10 秒后默认保存）"
read -t 10 -r ANS
if [[ -z "$ANS" || "$ANS" =~ ^[Yy] ]]; then
    cd /home/ws/ugv_ws || exit 1
    chmod +x ./save_2d_gmapping_map.sh
    ./save_2d_gmapping_map.sh
    echo "地图已保存到 src/ugv_main/ugv_nav/maps/（map.pgm / map.yaml）"
else
    echo "跳过保存。"
fi

echo "正在关闭建图节点..."
kill "$SLAM_PID" 2>/dev/null
wait "$SLAM_PID" 2>/dev/null
echo "完成。下一步：ros2 launch ugv_nav nav.launch.py use_rviz:=true 进行导航（或运行 run_target_nav.sh 一键目标导航）。"
