#!/usr/bin/env python3
"""检测算法离线验证：真实相机帧 + 合成红色目标。

取一帧真实 RGB 和一帧对齐深度图，在图像中央合成一个红色圆块和
1.5m 的深度盘，然后调用生产代码 TargetDetector.detect / sample_depth，
验证检测框、质心、深度采样和三维反投影是否正确。

用法（容器内）：
  source /opt/ros/humble/setup.bash
  source /home/ws/ugv_ws/install/setup.bash
  python3 test_detection_synth.py
"""

import os
import sys

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image

from ugv_nav_target.target_detector import TargetDetector


class FrameGrab(Node):
    def __init__(self):
        super().__init__('frame_grab')
        self.bridge = CvBridge()
        self.rgb = None
        self.depth = None
        self.info = None
        self.create_subscription(
            Image, '/oak/rgb/image_rect', self.rgb_cb, qos_profile_sensor_data)
        self.create_subscription(
            Image, '/oak/stereo/image_raw', self.depth_cb, qos_profile_sensor_data)
        self.create_subscription(
            CameraInfo, '/oak/rgb/camera_info', self.info_cb, qos_profile_sensor_data)

    def rgb_cb(self, msg):
        if self.rgb is None:
            self.rgb = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

    def depth_cb(self, msg):
        if self.depth is None:
            d = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            self.depth = d.astype(np.float32) * 0.001

    def info_cb(self, msg):
        if self.info is None:
            self.info = msg


def main():
    rclpy.init()
    node = FrameGrab()
    while node.rgb is None or node.depth is None or node.info is None:
        rclpy.spin_once(node, timeout_sec=1.0)
    rgb = node.rgb.copy()
    depth = node.depth.copy()
    k = node.info.k
    node.destroy_node()
    rclpy.shutdown()

    # ---- 合成目标：中心红点 + 1.5m 深度盘 ----
    h, w = rgb.shape[:2]
    cx, cy, r = w // 2, h // 2, 60
    cv2.circle(rgb, (cx, cy), r, (0, 0, 255), -1)  # BGR 纯红
    cv2.circle(depth, (cx, cy), r, 1.5, -1)
    print(f'合成目标: 圆心=({cx},{cy}) 半径={r} 深度=1.50m')

    # ---- 用生产代码检测 ----
    dummy = type('D', (), {})()
    dummy.hsv_ranges = [[0, 120, 70, 10, 255, 255], [170, 120, 70, 180, 255, 255]]
    dummy.min_area = 300
    dummy.depth_img = depth
    dummy.min_depth = 0.1
    dummy.max_depth = 6.0

    result, mask = TargetDetector.detect(dummy, rgb)
    assert result is not None, '未检测到合成红块！'
    (bbox, (dcx, dcy)) = result
    x, y, bw, bh = bbox
    print(f'检测框: {bbox}  质心: ({dcx},{dcy})')
    assert abs(dcx - cx) < 8 and abs(dcy - cy) < 8, '质心偏差过大'

    d = TargetDetector.sample_depth(dummy, bbox, dcx, dcy)
    print(f'采样深度: {d:.3f} m (期望 ~1.50)')
    assert d is not None and abs(d - 1.5) < 0.05, '深度采样错误'

    # ---- 三维反投影（生产代码 target_detector.py:197-199 的逻辑）----
    fx, fy, cxp, cyp = k[0], k[4], k[2], k[5]
    px = (dcx - cxp) * d / fx
    py = (dcy - cyp) * d / fy
    pz = d
    dist = (px * px + py * py + pz * pz) ** 0.5
    print(f'相机内参 fx={fx:.1f} fy={fy:.1f} cx={cxp:.1f} cy={cyp:.1f}')
    print(f'三维坐标: ({px:.3f}, {py:.3f}, {pz:.3f})  距离 {dist:.3f} m')
    assert abs(dist - 1.5) < 0.05, '反投影距离错误'

    vis = rgb.copy()
    cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
    cv2.circle(vis, (dcx, dcy), 4, (255, 0, 0), -1)
    cv2.putText(vis, f'target {d:.2f}m', (x, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'synth_test_out.png')
    cv2.imwrite(out, vis)
    print(f'验证通过，示意图已保存: {out}')
    print('SYNTH_TEST_PASS')


if __name__ == '__main__':
    sys.exit(main())
