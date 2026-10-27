#!/usr/bin/env python3
"""单目视觉目标检测器（headless，可直接使用）。

流程：订阅 USB 相机 /image_raw → HSV 双区间阈值分割 → 形态学去噪 →
最大连通块（>=min_area）→ 基于目标实际宽度与相机内参的针孔测距 →
TF 转换到 map 系 → 稳定 N 帧后发布 /ugv_auto/target_pose。

测距原理：d = target_width_m * fx / bbox_width_px（单目测距，精度受目标
尺寸误差与视角影响，配合 approach_manager 的接近距离限位与安全停止使用）。
"""
import math

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Float32MultiArray, String
from tf2_ros import Buffer, TransformListener

from tf2_geometry_msgs import do_transform_point
from geometry_msgs.msg import PointStamped


class MonoDetector(Node):
    def __init__(self):
        super().__init__('mono_detector')

        # ---- 参数 ----
        self.declare_parameter('hsv_lower1', [0, 120, 70])
        self.declare_parameter('hsv_upper1', [10, 255, 255])
        self.declare_parameter('hsv_lower2', [170, 120, 70])
        self.declare_parameter('hsv_upper2', [180, 255, 255])
        self.declare_parameter('min_area', 300)
        self.declare_parameter('target_width_m', 0.15)
        self.declare_parameter('min_dist', 0.3)
        self.declare_parameter('max_dist', 6.0)
        self.declare_parameter('stable_frames', 5)
        self.declare_parameter('rearm_frames', 30)
        self.declare_parameter('camera_frame', 'pt_camera_link')
        self.declare_parameter('publish_annotated', True)

        self.lower1 = np.array(self.get_parameter('hsv_lower1').value, np.uint8)
        self.upper1 = np.array(self.get_parameter('hsv_upper1').value, np.uint8)
        self.lower2 = np.array(self.get_parameter('hsv_lower2').value, np.uint8)
        self.upper2 = np.array(self.get_parameter('hsv_upper2').value, np.uint8)
        self.min_area = int(self.get_parameter('min_area').value)
        self.target_width = float(self.get_parameter('target_width_m').value)
        self.min_dist = float(self.get_parameter('min_dist').value)
        self.max_dist = float(self.get_parameter('max_dist').value)
        self.stable_frames = int(self.get_parameter('stable_frames').value)
        self.rearm_frames = int(self.get_parameter('rearm_frames').value)
        self.camera_frame = self.get_parameter('camera_frame').value

        # ---- 状态 ----
        self.bridge = CvBridge()
        self.fx = self.fy = self.cx = self.cy = None   # 来自 /camera_info
        self.stable = 0
        self.rearm = 0
        self.last_xy = None
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # ---- 话题 ----
        self.create_subscription(Image, '/image_raw', self.image_cb, 10)
        self.create_subscription(CameraInfo, '/camera_info', self.info_cb, 10)
        self.pub_pose = self.create_publisher(PoseStamped, '/ugv_auto/target_pose', 10)
        self.pub_dbg = self.create_publisher(Float32MultiArray, '/ugv_auto/detection', 10)
        self.pub_img = self.create_publisher(Image, '/ugv_auto/annotated_image', 10)
        self.pub_stat = self.create_publisher(String, '/ugv_auto/detector_status', 10)
        self.get_logger().info('mono_detector 已启动，等待 /image_raw ...')

    def info_cb(self, msg):
        if self.fx is None:
            k = msg.k
            self.fx, self.fy = k[0], k[4]
            self.cx, self.cy = k[2], k[5]
            self.get_logger().info(
                f'相机内参: fx={self.fx:.1f} fy={self.fy:.1f} cx={self.cx:.1f} cy={self.cy:.1f}')

    def detect(self, bgr):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.bitwise_or(cv2.inRange(hsv, self.lower1, self.upper1),
                              cv2.inRange(hsv, self.lower2, self.upper2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue
            if best is None or area > best[2]:
                x, y, w, h = cv2.boundingRect(cnt)
                m = cv2.moments(cnt)
                if m['m00'] == 0:
                    continue
                best = ((x, y, w, h), (int(m['m10'] / m['m00']), int(m['m01'] / m['m00'])), area)
        return best, mask

    def image_cb(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        vis = frame.copy() if self.get_parameter('publish_annotated').value else None

        if self.fx is None or self.rearm > 0:
            if self.rearm > 0:
                self.rearm -= 1
            if vis is not None:
                self.pub_img.publish(self.bridge.cv2_to_imgmsg(vis, 'bgr8'))
            return

        best, _mask = self.detect(frame)
        if best is None:
            self.stable = 0
            self.last_xy = None
            if vis is not None:
                self.pub_img.publish(self.bridge.cv2_to_imgmsg(vis, 'bgr8'))
            return

        (x, y, w, h), (cx, cy), area = best
        d = self.target_width * self.fx / max(1, w)
        ok = self.min_dist <= d <= self.max_dist
        if vis is not None:
            color = (0, 255, 0) if ok else (0, 165, 255)
            cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
            cv2.circle(vis, (cx, cy), 4, (255, 0, 0), -1)
            cv2.putText(vis, f'{d:.2f}m', (x, max(20, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            self.pub_img.publish(self.bridge.cv2_to_imgmsg(vis, 'bgr8'))
        dbg = Float32MultiArray(data=[float(cx), float(cy), float(d), float(area)])
        self.pub_dbg.publish(dbg)
        if not ok:
            self.stable = 0
            return

        # 稳定判定：连续帧且质心漂移小
        if self.last_xy is not None and \
           math.hypot(cx - self.last_xy[0], cy - self.last_xy[1]) < 40:
            self.stable += 1
        else:
            self.stable = 1
        self.last_xy = (cx, cy)
        if self.stable < self.stable_frames:
            return

        # 反投影到相机系（光心坐标：z 前 x 右 y 下）
        px = (cx - self.cx) * d / self.fx
        py = (cy - self.cy) * d / self.fy
        pz = d
        # 经 TF 转到 map 系
        try:
            tf = self.tf_buffer.lookup_transform(
                'map', self.camera_frame, rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=0.5))
        except Exception as e:
            self.get_logger().warn(f'TF 查询失败(map<-{self.camera_frame}): {e}')
            return
        pt_cam = PointStamped()
        pt_cam.header.frame_id = self.camera_frame
        pt_cam.header.stamp = msg.header.stamp
        pt_cam.point.x, pt_cam.point.y, pt_cam.point.z = px, py, pz
        pt_map = do_transform_point(pt_cam, tf)

        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = pt_map.point.x
        pose.pose.position.y = pt_map.point.y
        pose.pose.position.z = 0.0
        # 朝向：机器人当前位置指向目标
        try:
            tf_base = self.tf_buffer.lookup_transform(
                'map', 'base_footprint', rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=0.5))
            bx, by = tf_base.transform.translation.x, tf_base.transform.translation.y
            yaw = math.atan2(pt_map.point.y - by, pt_map.point.x - bx)
        except Exception:
            yaw = 0.0
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.pub_pose.publish(pose)
        self.rearm = self.rearm_frames
        self.stable = 0
        self.get_logger().info(
            f'发布目标: map({pose.pose.position.x:.2f}, {pose.pose.position.y:.2f}) '
            f'距离 {d:.2f}m')
        self.pub_stat.publish(String(data=f'TARGET_PUBLISHED {d:.2f}m'))


def main():
    rclpy.init()
    node = MonoDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()
