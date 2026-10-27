# ugv_auto —— UGV Beast 一体式项目包

把散落的模块整合成一条可直接使用的工作流：**手柄遥控建图 → 保存地图 → Nav2 导航 + 单目视觉识别 → 自动接近目标**。

## 依赖（容器内均已安装）

- ugv_slam / ugv_nav / ugv_vision / ugv_tools（本工作空间）
- joy（手柄驱动）、Nav2 1.1.16、Cartographer、usb_cam

## 快速开始

```bash
cd /home/ws/ugv_ws
colcon build --packages-select ugv_auto --symlink-install
source install/setup.bash
bash $(ros2 pkg prefix ugv_auto)/share/ugv_auto/scripts/run_project.sh
```

菜单三项按顺序执行：

1. **手柄遥控建图**——插入手柄（/dev/input/js0），低速绕场一周覆盖场地；
   结束后按提示保存地图（map.pgm/yaml + map.pbstream）。
2. **保存地图**——随时可单独执行。
3. **导航+识别**——启动后在 RViz 中点 `2D Pose Estimate` 给出初始位姿，
   将红色目标（默认宽 15 cm，config/target.yaml 可改）放入视野 0.3~6 m，
   机器人自动规划路径开到目标前 0.35 m 处；识别画面见话题
   `/ugv_auto/annotated_image`，任务状态见 `/ugv_auto/status`。

## 节点说明

| 节点 | 输入 | 输出 | 职责 |
|---|---|---|---|
| mono_detector | /image_raw、/camera_info、TF | /ugv_auto/target_pose（map 系）、/ugv_auto/annotated_image | HSV 阈值+形态学检测红色目标，单目测距（d=W·fx/w），稳定 5 帧后经 TF 发布 map 系目标位姿 |
| approach_manager | /ugv_auto/target_pose | Nav2 NavigateToPose、/ugv_auto/status | 计算接近点（目标前 0.35 m），发导航目标；目标移动 >0.3 m 自动重规划；失败重试 ≤3 次；退出时取消目标并置零速 |

## 目录结构

```
ugv_auto/
├── launch/stage1_mapping_joy.launch.py   # 手柄 + Cartographer 建图
├── launch/stage2_nav_vision.launch.py    # Nav2 + 相机 + 检测 + 任务管理
├── config/target.yaml                    # 识别与接近参数
├── scripts/run_project.sh                # 一键菜单
├── scripts/save_map.sh                   # 保存地图
└── ugv_auto/                             # mono_detector / approach_manager
```

## 实测记录（2026-10-21/22，履带架空条件）

- 检测器：80 个合成样本（正面/远距/遮挡）正确率 100%，30 帧负样本 0 误检；
- 端到端集成测试（2026-10-22 E2E_PASS）：合成图像注入 → mono_detector 发布
  map 系目标（1.11 m，期望 1.08 m，测距误差约 3%）→ approach_manager 接近点
  （目标前 0.35 m）→ Nav2 NavigateToPose 接受并进入 NAVIGATING；
- 手柄链路：模拟 /joy 验证 joy_teleop→cmd_vel（0.35 m/s，含 0.7 档速比）→
  底盘编码器响应 → 松开自动归零；stage1 冒烟测试节点齐全、/map 1 Hz；
- 导航物理到达：待落地后按相同流程复测（架空条件 map 系位姿不变，Goal failed 属预期）。

## 已知边界

- 单目测距精度约 ±20%~30%（依赖目标宽度标定与正对视角），近距离接近请保持场地空旷；
- 夜间建议开启补光灯（下位机 IO5）；
- 同一时刻只能运行一个含 bringup 的 launch（脚本已做清理）。
