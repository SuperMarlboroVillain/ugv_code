"""OpenCV 颜色目标识别节点。

订阅相机 RGB 图像（/oak/rgb/image_rect），在 HSV 色彩空间中检测指定颜色的
目标（默认检测红色物体，例如红色小球），结合对齐深度图（/oak/stereo/image_raw）
解算目标的三维位置，并通过 TF 变换到 map 坐标系后发布，供导航节点使用。

发布话题：
  /target_detector/annotated_image  (sensor_msgs/Image)   标注了检测结果的图像，可在 RViz 中查看
  /target_detector/target_pose      (geometry_msgs/PoseStamped)  目标在 map 系下的位置

服务：
  /target_detector/reset            (std_srvs/Trigger)  清除已发布锁存，立即重新武装检测
  另外：目标连续丢失 rearm_frames 帧后自动重新武装，支持"追球"场景反复触发。
"""

import math

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped, PoseStamped
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_srvs.srv import Trigger
from tf2_geometry_msgs import do_transform_point
from tf2_ros import TransformException
from tf2_ros import Buffer, TransformListener


class TargetDetector(Node):
    def __init__(self):
        super().__init__("target_detector")

        # ---- 参数 ----
        self.declare_parameter("image_topic", "/oak/rgb/image_rect")
        self.declare_parameter("depth_topic", "/oak/stereo/image_raw")
        self.declare_parameter("camera_info_topic", "/oak/rgb/camera_info")
        self.declare_parameter("annotated_topic", "/target_detector/annotated_image")
        self.declare_parameter("pose_topic", "/target_detector/target_pose")
        self.declare_parameter("target_frame", "map")
        self.declare_parameter("min_area_px", 300)
        self.declare_parameter("stable_frames", 5)
        self.declare_parameter("max_depth_m", 4.0)
        self.declare_parameter("min_depth_m", 0.1)
        # 目标丢失多少帧后自动重新武装（0=关闭自动重武装）。追球场景：
        # 人把球拿走后，检测不到目标，超过该帧数后允许再次发布新目标。
        self.declare_parameter("rearm_frames", 30)
        # HSV 阈值范围，扁平列表，每 6 个数一组：
        # [h_lo, s_lo, v_lo, h_hi, s_hi, v_hi, ...]
        # 红色跨 0 度需要两组；检测其它颜色一组即可。
        self.declare_parameter(
            "hsv_ranges", [0, 120, 70, 10, 255, 255, 170, 120, 70, 180, 255, 255]
        )

        self.image_topic = self.get_parameter("image_topic").value
        self.depth_topic = self.get_parameter("depth_topic").value
        self.camera_info_topic = self.get_parameter("camera_info_topic").value
        self.target_frame = self.get_parameter("target_frame").value
        self.min_area = int(self.get_parameter("min_area_px").value)
        self.stable_frames = int(self.get_parameter("stable_frames").value)
        self.max_depth = float(self.get_parameter("max_depth_m").value)
        self.min_depth = float(self.get_parameter("min_depth_m").value)
        flat = [int(v) for v in self.get_parameter("hsv_ranges").value]
        if len(flat) % 6 != 0:
            raise ValueError("hsv_ranges 长度必须是 6 的倍数（每 6 个数一组 HSV 范围）")
        self.hsv_ranges = [flat[i:i + 6] for i in range(0, len(flat), 6)]

        self.get_logger().info(f"识别颜色范围 HSV: {self.hsv_ranges}")

        # ---- 运行时调参（PRD FR-08 规则1：阈值现场调整即时生效；
        #      FR-12 规则4：越界拒绝并说明合法区间）。支持 ros2 param set / rqt_reconfigure ----
        self.add_on_set_parameters_callback(self.on_params)

        # ---- 状态 ----
        self.bridge = CvBridge()
        self.camera_info = None
        self.depth_img = None
        self.stable_count = 0
        self.pose_published = False
        self.miss_count = 0
        self.rearm_frames = int(self.get_parameter("rearm_frames").value)

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # ---- 订阅与发布 ----
        self.create_subscription(Image, self.image_topic, self.image_cb, 10)
        self.create_subscription(Image, self.depth_topic, self.depth_cb, 10)
        self.create_subscription(CameraInfo, self.camera_info_topic, self.info_cb, 10)
        self.ann_pub = self.create_publisher(Image, self.get_parameter("annotated_topic").value, 10)
        self.pose_pub = self.create_publisher(PoseStamped, self.get_parameter("pose_topic").value, 10)
        self.create_service(Trigger, "/target_detector/reset", self.reset_cb)

        self.get_logger().info(
            f"等待图像: {self.image_topic}  深度: {self.depth_topic}  相机信息: {self.camera_info_topic}"
        )

    def on_params(self, params):
        """运行时调参回调（FR-08 规则1 即时生效；FR-12 规则4 越界拒绝）。"""
        from rcl_interfaces.msg import SetParametersResult
        ok, reasons = True, []
        for p in params:
            if p.name == "hsv_ranges":
                flat = [int(v) for v in p.value]
                if not flat or len(flat) % 6 != 0:
                    ok = False
                    reasons.append(f"hsv_ranges 长度须为 6 的倍数，收到 {len(flat)} 个")
                    continue
                bad = [i for i, v in enumerate(flat)
                       if not (0 <= v <= (180 if i % 6 in (0, 3) else 255))]
                if bad:
                    ok = False
                    reasons.append(f"hsv_ranges 越界(索引 {bad}; H:0-180, S/V:0-255)")
                    continue
                self.hsv_ranges = [flat[i:i + 6] for i in range(0, len(flat), 6)]
                self.get_logger().info(f"[在线调参] HSV 已更新: {self.hsv_ranges}")
            elif p.name == "min_area_px":
                v = int(p.value)
                if not 10 <= v <= 100000:
                    ok = False; reasons.append("min_area_px 合法区间 10~100000")
                else:
                    self.min_area = v
                    self.get_logger().info(f"[在线调参] min_area_px={v}")
            elif p.name == "min_depth_m":
                v = float(p.value)
                if not 0.05 <= v < self.max_depth:
                    ok = False; reasons.append(f"min_depth_m 须满足 0.05 <= v < max_depth({self.max_depth})")
                else:
                    self.min_depth = v
                    self.get_logger().info(f"[在线调参] min_depth_m={v}")
            elif p.name == "max_depth_m":
                v = float(p.value)
                if not self.min_depth < v <= 10.0:
                    ok = False; reasons.append(f"max_depth_m 须满足 min_depth({self.min_depth}) < v <= 10.0")
                else:
                    self.max_depth = v
                    self.get_logger().info(f"[在线调参] max_depth_m={v}")
            elif p.name in ("stable_frames", "rearm_frames"):
                v = int(p.value)
                if not 1 <= v <= 300:
                    ok = False; reasons.append(f"{p.name} 合法区间 1~300")
                else:
                    setattr(self, p.name, v)
                    self.get_logger().info(f"[在线调参] {p.name}={v}")
            else:
                ok = False
                reasons.append(f"{p.name} 不支持在线修改（请改 config/target_detect.yaml 后重启）")
        return SetParametersResult(successful=ok, reason="; ".join(reasons))

    # ------------------------------------------------------------------
    def reset_cb(self, request, response):
        """手动清除已发布锁存，立即重新武装检测。"""
        self.pose_published = False
        self.stable_count = 0
        self.miss_count = 0
        self.get_logger().info("收到 reset，检测已重新武装")
        response.success = True
        response.message = "detector rearmed"
        return response

    def info_cb(self, msg):
        self.camera_info = msg

    def depth_cb(self, msg):
        try:
            cv_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"深度图转换失败: {exc}")
            return
        # depthai 输出 16UC1（毫米）或 32FC1（米），统一转成 float 米制
        if cv_depth.dtype == np.uint16:
            cv_depth = cv_depth.astype(np.float32) * 0.001
        self.depth_img = cv_depth
        self.depth_frame_id = msg.header.frame_id

    # ------------------------------------------------------------------
    def detect(self, bgr):
        """返回按面积降序排列的候选列表 [(bbox, (cx, cy), area), ...]。

        形态学顺序：先 CLOSE（填补目标中心的过曝空洞，再轻微 OPEN 去噪点。
        直接 OPEN×2 会把'边缘红、中心白'的目标（反光小球）整个腐蚀掉。
        """
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = None
        for r in self.hsv_ranges:
            lo = np.array(r[0:3], dtype=np.uint8)
            hi = np.array(r[3:6], dtype=np.uint8)
            m = cv2.inRange(hsv, lo, hi)
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        if mask is None:
            return [], None
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cands = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue
            moments = cv2.moments(cnt)
            if moments["m00"] == 0:
                continue
            cx = int(moments["m10"] / moments["m00"])
            cy = int(moments["m01"] / moments["m00"])
            cands.append((cv2.boundingRect(cnt), (cx, cy), area))
        cands.sort(key=lambda c: c[2], reverse=True)
        return cands, mask

    def sample_depth(self, bbox, cx, cy):
        """取 bbox 中心 1/3 区域内有效深度的中位数（米）。"""
        if self.depth_img is None:
            return None
        x, y, w, h = bbox
        w3, h3 = max(1, w // 3), max(1, h // 3)
        x0, x1 = max(0, cx - w3), min(self.depth_img.shape[1], cx + w3)
        y0, y1 = max(0, cy - h3), min(self.depth_img.shape[0], cy + h3)
        region = self.depth_img[y0:y1, x0:x1]
        valid = region[np.isfinite(region) & (region > self.min_depth) & (region < self.max_depth)]
        if valid.size == 0:
            return None
        return float(np.median(valid))

    # ------------------------------------------------------------------
    def image_cb(self, msg):
        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"图像转换失败: {exc}")
            return

        cands, mask = self.detect(bgr)
        annotated = bgr.copy()

        if not cands:
            self.stable_count = 0
            self.miss_count += 1
            if (
                self.rearm_frames > 0
                and self.pose_published
                and self.miss_count >= self.rearm_frames
            ):
                self.pose_published = False
                self.miss_count = 0
                self.get_logger().info("目标丢失，已自动重新武装检测")
            self.ann_pub.publish(self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8"))
            return

        self.miss_count = 0

        # 深度优先：从大到小尝试候选块，第一个深度有效者即为目标。
        # 避免远处的大块红色干扰物（如场地边缘物体）挡住近处的真目标。
        chosen = None
        for bbox, (cx, cy), _area in cands[:5]:
            depth = self.sample_depth(bbox, cx, cy)
            if depth is not None:
                chosen = (bbox, (cx, cy), depth)
                break

        if chosen is None:
            # 所有候选都没有有效深度，画出最大的一个便于调试
            bbox, (cx, cy), _ = cands[0]
            x, y, w, h = bbox
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(annotated, (cx, cy), 4, (255, 0, 0), -1)
            cv2.putText(annotated, "target (no depth)", (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            self.stable_count = 0
            self.ann_pub.publish(self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8"))
            return

        (bbox, (cx, cy), depth) = chosen
        x, y, w, h = bbox
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(annotated, (cx, cy), 4, (255, 0, 0), -1)
        cv2.putText(annotated, f"target {depth:.2f}m", (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        self.ann_pub.publish(self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8"))

        # ---- 连续多帧稳定后只发布一次位姿 ----
        self.stable_count += 1
        if self.stable_count < self.stable_frames or self.pose_published:
            return

        if self.camera_info is None:
            self.get_logger().warn("还没有 camera_info，无法解算三维坐标")
            return

        # 像素坐标 -> 相机光心坐标系
        k = self.camera_info.k
        fx, fy = k[0], k[4]
        cxp, cyp = k[2], k[5]
        if fx == 0 or fy == 0:
            self.get_logger().warn("camera_info 内参无效")
            return
        px = (cx - cxp) * depth / fx
        py = (cy - cyp) * depth / fy
        pz = depth

        src_frame = getattr(self, "depth_frame_id", None) or msg.header.frame_id
        point_cam = PointStamped()
        point_cam.header.frame_id = src_frame
        point_cam.header.stamp = msg.header.stamp
        point_cam.point.x = px
        point_cam.point.y = py
        point_cam.point.z = pz

        # TF 到目标坐标系（默认 map）
        try:
            transform = self.tf_buffer.lookup_transform(
                self.target_frame, src_frame, rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=1.0)
            )
        except TransformException as exc:
            self.get_logger().warn(f"TF 查询失败 ({src_frame} -> {self.target_frame}): {exc}")
            return

        point_map = do_transform_point(point_cam, transform)
        pose = PoseStamped()
        pose.header.frame_id = self.target_frame
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = point_map.point.x
        pose.pose.position.y = point_map.point.y
        pose.pose.position.z = point_map.point.z
        pose.pose.orientation.w = 1.0
        self.pose_pub.publish(pose)
        self.pose_published = True

        dist = math.sqrt(px * px + py * py + pz * pz)
        self.get_logger().info(
            f"识别到目标！map 系坐标: ({pose.pose.position.x:.2f}, "
            f"{pose.pose.position.y:.2f})，距离 {dist:.2f} m，已发布到 {self.pose_pub.topic_name}"
        )


def main():
    rclpy.init()
    node = TargetDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
