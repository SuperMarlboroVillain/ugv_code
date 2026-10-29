#!/bin/bash
# ugv_auto 一键项目脚本：建图 → 存图 → 导航+识别
# 用法：bash run_project.sh   （或在容器内直接执行）
set -u
WS=/home/ws/ugv_ws

source /opt/ros/humble/setup.bash
source $WS/install/setup.bash
export UGV_MODEL=ugv_beast
export LDLIDAR_MODEL=ld19

cleanup() {
    echo; echo "正在关闭所有节点..."
    pkill -f '[u]gv_auto' 2>/dev/null
    pkill -f '[s]tage1_mapping_joy' 2>/dev/null
    pkill -f '[s]tage2_nav_vision' 2>/dev/null
    pkill -f '[c]artographer' 2>/dev/null
    pkill -f '[n]av.launch' 2>/dev/null
    pkill -f '[j]oy_node' 2>/dev/null
    pkill -f '[m]ono_detector' 2>/dev/null
    pkill -f '[a]pproach_manager' 2>/dev/null
}
trap cleanup INT TERM

kill_leftover() {
    # 只允许一个 bringup 实例运行，防止串口争抢
    pkill -f '[b]ringup_lidar' 2>/dev/null
    pkill -f '[l]dlidar_node' 2>/dev/null
    pkill -f '[b]ase_node' 2>/dev/null
    pkill -f '[u]gv_bringup' 2>/dev/null
    pkill -f '[u]gv_driver' 2>/dev/null
    sleep 2
}

while true; do
    echo "=============================================="
    echo " UGV Beast 一体式项目"
    echo "  1) 手柄遥控建图（Cartographer）"
    echo "  2) 保存地图"
    echo "  3) 导航 + 视觉识别 + 自动接近目标"
    echo "  4) 退出"
    echo "=============================================="
    read -r -p "请选择 [1-4]: " CHOICE
    case "$CHOICE" in
        1)
            kill_leftover
            echo "启动建图。用手柄低速绕场一周，尽量覆盖整个场地。"
            echo "完成后回到本终端按 Ctrl+C 结束建图。"
            (trap '' INT; exec ros2 launch ugv_auto stage1_mapping_joy.launch.py use_rviz:=true) &
            SLAM_PID=$!
            trap 'echo; echo "建图结束。"' INT
            wait $SLAM_PID
            read -r -p "是否保存地图？[Y/n] " ANS
            if [[ -z "$ANS" || "$ANS" =~ ^[Yy] ]]; then
                bash "$(ros2 pkg prefix ugv_auto)/share/ugv_auto/scripts/save_map.sh"
            fi
            ;;
        2)
            bash "$(ros2 pkg prefix ugv_auto)/share/ugv_auto/scripts/save_map.sh"
            ;;
        3)
            kill_leftover
            echo "启动导航+识别。"
            echo "步骤：1. RViz 点 '2D Pose Estimate' 指出初始位姿"
            echo "      2. 把红色目标(默认15cm宽)放至视野内 0.3~6 m"
            echo "      3. 机器人自动开到目标前 0.35 m 处"
            echo "      4. 识别画面: RViz -> /ugv_auto/annotated_image"
            echo "按 Ctrl+C 退出。"
            ros2 launch ugv_auto stage2_nav_vision.launch.py use_rviz:=true
            ;;
        4)
            cleanup
            exit 0
            ;;
        *)
            echo "无效选择";;
    esac
done
