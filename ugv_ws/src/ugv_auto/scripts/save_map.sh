#!/bin/bash
# 保存 Cartographer 地图（pgm/yaml + pbstream），供 Nav2 加载
set -u
WS=/home/ws/ugv_ws
MAP_DIR=$WS/src/ugv_main/ugv_nav/maps

source /opt/ros/humble/setup.bash
source $WS/install/setup.bash

echo "保存地图到 $MAP_DIR ..."
mkdir -p "$MAP_DIR"
ros2 run nav2_map_server map_saver_cli -f "$MAP_DIR/map" || exit 1
ros2 service call /write_state cartographer_ros_msgs/srv/WriteState \
    "{filename: '$MAP_DIR/map.pbstream'}" || true
echo "完成: map.pgm / map.yaml / map.pbstream"
