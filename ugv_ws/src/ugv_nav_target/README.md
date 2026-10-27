# UGV Beast 自主导航 + OpenCV 目标识别

基于微雪 UGV Beast Jetson Orin ROS2 教程环境（Humble）实现：

1. **2D SLAM 建图**（激光雷达 gmapping）→ 保存地图
2. **Nav2 路径规划导航**（AMCL 定位 + TEB 局部规划）
3. **OpenCV 视觉目标识别**（HSV 颜色检测 + OAK-D Lite 深度测距）
4. 识别到目标后**自动导航到目标所在位置**

## 文件结构

```
ugv_nav_target/
├── ugv_nav_target/
│   ├── target_detector.py   # OpenCV 颜色目标识别 + 深度测距 + TF 变换节点
│   └── goal_sender.py       # 收到目标位置后调用 Nav2 NavigateToPose 动作
├── launch/
│   ├── oak_camera_aligned.launch.py  # OAK 相机（深度对齐 RGB）
│   └── target_nav.launch.py          # 一键启动识别+导航节点
├── config/
│   ├── target_detect.yaml            # 识别参数（颜色/面积/深度范围）
│   └── oak_d_lite_aligned.yaml       # 相机参数（开启深度对齐）
└── scripts/
    ├── build_2d_map.sh      # 第一步：建图 + 保存地图
    └── run_target_nav.sh    # 第二步：导航 + 识别 + 自动开往目标
```

## 使用流程

以下命令都在 Docker 容器终端里执行（`docker exec -it ugv_jetson_ros_humble bash`）。

### 0. 编译（只做一次）

```bash
cd /home/ws/ugv_ws
colcon build --packages-select ugv_nav_target --symlink-install
source ~/.bashrc   # 或 source install/setup.bash
```

### 第一步：建图

```bash
/home/ws/ugv_ws/src/ugv_nav_target/scripts/build_2d_map.sh
```

键盘控制小车把环境扫完（w/s/a/d 移动，空格急停），然后按 `Ctrl+C`，
按提示保存地图（默认 map，保存到 `src/ugv_main/ugv_nav/maps/`）。

### 第二步：目标导航

```bash
/home/ws/ugv_ws/src/ugv_nav_target/scripts/run_target_nav.sh
```

1. RViz 中点 **2D Pose Estimate** 设定机器人初始位姿；
2. 把红色物体（默认检测红色）放在机器人前方地面 0.3~6 m；
3. 识别稳定后机器人自动规划路径开过去，到达后停止；
4. 想取消重来：`ros2 service call /target_detector/reset std_srvs/srv/Trigger`；
5. 想看识别画面：RViz → Add → By topic → `/target_detector/annotated_image`。

## 自定义目标颜色

**方式一（启动时指定，2026-10-27 新增）**：launch 参数 `target_color`，
覆盖 yaml 默认红色，无需改文件：

```bash
ros2 launch ugv_nav_target target_nav.launch.py target_color:=green   # red/green/blue/yellow/custom
```

**方式二（运行中在线调，2026-10-27 新增，真正生效）**：`target_detector`
已注册动态参数回调，支持 rqt_reconfigure 或命令行，即时生效、越界拒绝并提示合法区间：

```bash
ros2 param set /target_detector hsv_ranges "[35,80,80,85,255,255]"   # 绿色
ros2 param set /target_detector min_area_px 500
```

可在线调：hsv_ranges / min_area_px / min_depth_m / max_depth_m / stable_frames / rearm_frames。

**方式三（改默认）**：编辑 `config/target_detect.yaml` 里的 `hsv_ranges`（HSV 阈值）：

| 颜色 | hsv_ranges |
|------|-----------|
| 红色(默认) | `[0,120,70,10,255,255,170,120,70,180,255,255]` |
| 绿色 | `[35,80,80,85,255,255]` |
| 蓝色 | `[100,120,70,130,255,255]` |
| 黄色 | `[20,120,120,40,255,255]` |

改完重新运行即可（launch 会重新加载参数；若想边调边看可用
`ros2 run rqt_reconfigure rqt_reconfigure` 在线调 HSV）。

## 话题接口

| 话题 | 类型 | 说明 |
|------|------|------|
| `/target_detector/annotated_image` | sensor_msgs/Image | 标注了检测框和距离的图像 |
| `/target_detector/target_pose` | geometry_msgs/PoseStamped | 目标在 map 系下的位置 |
| `/target_detector/reset` (service) | std_srvs/Trigger | 取消当前导航、重新待命 |

## 工作原理

1. `target_detector` 在 `/oak/rgb/image_rect` 上做 HSV 阈值分割 + 形态学去噪，
   取最大连通块为目标；在深度图 `/oak/stereo/image_raw` 的目标区域取深度中位数，
   用相机内参反投影得到相机系三维坐标，经 TF 转到 `map` 系发布；
2. `goal_sender` 订阅目标位置，调用 Nav2 的 `NavigateToPose` 动作完成路径规划，
   目标移动超过阈值时自动重规划。
