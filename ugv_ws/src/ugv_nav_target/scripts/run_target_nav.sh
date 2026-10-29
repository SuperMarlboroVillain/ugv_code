#!/bin/bash
# 第二步：一键启动 自主导航 + OAK 相机 + OpenCV 目标识别 + 自动导航到目标
# 前置：已经用 build_2d_map.sh 建好并保存了地图（src/ugv_main/ugv_nav/maps/map.yaml）
# 用法：在 Docker 容器终端中执行本脚本
set -u
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash 2>/dev/null
# nav.launch.py 链需要机型环境变量（stage1_mapping_joy 是在 launch 里设置的，这里手动补）
export UGV_MODEL=ugv_beast LDLIDAR_MODEL=ld19

cleanup() {
    echo; echo "正在关闭所有节点..."
    kill 0
}
trap cleanup INT TERM

echo "=============================================="
echo " 启动导航(AMCL+TEB) + RViz ..."
ros2 launch ugv_nav nav.launch.py use_localization:=amcl use_localplan:=teb use_rviz:=true &
sleep 8

echo "启动 OAK-D Lite 相机（深度对齐 RGB）..."
ros2 launch ugv_nav_target oak_camera_aligned.launch.py &
sleep 12

echo "启动目标识别 + 导航目标发送节点..."
ros2 launch ugv_nav_target target_nav.launch.py "$@" &

echo "=============================================="
echo " 操作步骤："
echo "  1. 在 RViz 中点击 2D Pose Estimate，在地图上指出机器人的初始位置和朝向"
echo "  2. 把红色目标（默认识别红色，可改 config/target_detect.yaml）"
echo "     放在机器人视野内 0.3~6 m 的地面上"
echo "  3. 机器人识别到目标后会自动规划路径开过去"
echo "  4. 想看识别画面：RViz -> Add -> By topic -> /target_detector/annotated_image"
echo "  5. 想取消当前任务重来：ros2 service call /target_detector/reset std_srvs/srv/Trigger"
echo "  按 Ctrl+C 全部退出"
echo "=============================================="

wait
