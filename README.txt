UGV 自主导航与目标识别系统 —— 代码包 v2026-10-27
=====================================================

硬件：Waveshare UGV Beast（履带底盘）+ Jetson Orin Nano 4GB
环境：Ubuntu 22.04 + ROS 2 Humble（Docker 容器 ugv_jetson_ros_humble）
需求基线：~/Downloads/ROS2_Humble_自主导航与目标识别系统_PRD.md (v0.3)

目录结构
--------
ugv_ws/            ROS 2 工作空间源码（容器内挂载于 /home/ws/ugv_ws）
  src/             全部功能包源码：
                   ugv_auto(键盘遥控/检测) ugv_else(cartographer配置)
                   ugv_main(厂商包:bringup/slam/nav/vision/gazebo 等)
                   ugv_nav_target(目标识别+转导航，含 target_color 启动选色
                   与在线动态调参)
  *.sh, *.py       工作空间根目录工具脚本（保存地图/自动备份/OpenCV实验入口等）
home_scripts/      宿主机自动化脚本（部署到 ~ 并 chmod +x）：
                   ugv_ros.sh           进容器/执行ROS命令的万能入口
                   ugv_selfcheck.sh     就绪自检 13 项（FR-01，键鼠缺失仅警告）
                   ugv_mode.sh          会话模式管理 BENCH/ROS2/OPENCV/MANUAL（FR-02）
                   ugv_factory.sh       出厂程序 停止/禁用自启/恢复（FR-02 规则4）
                   *_menu.sh / *_gui.sh 上述脚本的桌面菜单封装
                   ugv_start_mapping.sh 一键建图（三标签页）
                   ugv_keyboard_teleop.sh / ugv_save_map_now.sh / auto_save_map.sh
                   harden_ugv.sh        内存加固（swap+earlyoom+sysctl）
desktop/           6 个桌面双击入口（拷到 ~/Desktop，右键"允许启动"）
docs/              扫图优化记录_2026-10-22.md（含 10-27 PRD 自查、FR-08 实测、
                   踩坑记录与差距表）+ crontab.txt + PRD_v0.3.md（需求原文）
                   + system_snapshot.txt（内存/swap/earlyoom/USB/容器状态）

报告证据数据（写报告用，10-27 按需求补入）
--------------------------------------------
ugv_ws/src/ugv_main/ugv_nav/maps/
  map.pgm/.yaml/.pbstream     当前正式地图（10-22 扫描成果，10-27 修复 0 字节事故后恢复）
  autosave/                   5 分钟级自动备份 23 份（10-23 冒烟会话，
                              map_20261023_101004 为配置调参验证依据）
maps_desktop/               桌面参考图：map_本次扫描.pgm（10-22 修复后）、
                            map_崩溃前备份.pgm（OOM 死机前）——前后对比素材
ugv_ws/test_out/            相机实测快照：usb_cam_snap.png（OpenCV 通路 640x480）、
                            oak_rgb_snap.png / oak_depth_snap.png（OAK 对齐深度）、
                            oak_launch.log、target_nav_test.log（动态调参验证）
logs/                       ugv_selfcheck.log（13 项自检记录）/ ugv_mode.log（模式切换
                            事件）/ autosave_map.log（自动备份服务日志）/
                            factory_app_ugv.log（出厂主程序被 OOM 终结的痕迹）
ugv_ws/src/ugv_else/cartographer/config/mapping_2d.lua.bak_20261022
                            参数调优前后对照（旧值备份）

本包不含（运行时产物，可随时再生成）
------------------------------------
ugv_ws/build|install|log   colcon 产物（重建即可）
容器镜像本身               （docker export 另算）

恢复到新机/新系统的步骤
------------------------
1. 拷回源码：ugv_ws/ 整体放到容器挂载的工作空间路径（默认 /home/ws/ugv_ws）
2. home_scripts/ 拷到 ~ 并 chmod +x *.sh
3. desktop/ 拷到 ~/Desktop 并 chmod +x
4. 容器内重建：cd /home/ws/ugv_ws && colcon build --symlink-install
5. crontab：参考 docs/crontab.txt 恢复 5 分钟地图自动备份
   （app.py 自启行保持注释 = 出厂 Web 主程序禁用状态）
6. 内存加固参考 harden_ugv.sh（swap 优先级 0 低于 zram 5）

日常使用顺序（双击图标或命令）
------------------------------
就绪自检 → 出厂程序管理(选3释放相机) → 会话模式(选模式后会自动询问启动实验)
收尾/排障请看 docs/扫图优化记录_2026-10-22.md 的"日常使用"与差距表。
