#!/bin/bash
# 键盘遥控守护包装（容器内运行；配合一键建图会话标签页）
# 行为: 键盘遥控保持可操作；一旦 cartographer_node 消失（建图被 Ctrl+C
#   自动保存并停止），只结束【本标签页自己启动的】遥控，绝不动其它窗口的遥控。
# 测试钩子: TELEOP_CMD 可用普通命令替代真实遥控做验证。
source /opt/ros/humble/setup.bash
source /home/ws/ugv_ws/install/setup.bash

${TELEOP_CMD:-ros2 run ugv_auto keyboard_teleop} &
TP=$!

(
  for _ in $(seq 1 45); do          # 90s 内等待建图起来（容差：容器慢/雷达慢）
    ros2 node list 2>/dev/null | grep -q cartographer_node && break
    sleep 2
  done
  while ros2 node list 2>/dev/null | grep -q cartographer_node; do
    sleep 2
  done
  echo; echo "===== 建图会话已结束（地图已自动保存），本标签页遥控退出 ====="
  # 注意: 非交互bash对 & 后台子进程默认忽略SIGINT(会过exec继承)，必须发SIGTERM
  kill -TERM "$TP" 2>/dev/null; sleep 3; kill -KILL "$TP" 2>/dev/null
) &

wait "$TP" 2>/dev/null
wait 2>/dev/null   # 等守护子shell收尾打印
