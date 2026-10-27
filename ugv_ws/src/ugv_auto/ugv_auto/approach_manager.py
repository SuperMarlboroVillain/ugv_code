#!/usr/bin/env python3
"""目标接近任务管理器 v2：识别 → 导航 → 到达/丢失。

订阅 /ugv_auto/target_pose（mono_detector 发布）：
- IDLE：收到目标 → 由定时器非阻塞发送 Nav2 NavigateToPose（接近点 = 目标沿
  机器人方向回退 stop_offset 米，避免撞上；距离已足够近时直接判 ARRIVED）。
- NAVIGATING：目标更新且移动 > replan_threshold → 取消重发（限 replan_limit 次）；
  SUCCEEDED → ARRIVED；失败用最新目标重试，超限 → 回到 IDLE 等待新目标。
- 全程异步回调，无阻塞调用；节点退出取消目标并置零速。
"""
import math

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


class ApproachManager(Node):
    def __init__(self):
        super().__init__('approach_manager')
        self.declare_parameter('stop_offset', 0.35)
        self.declare_parameter('arrive_slack', 0.15)
        self.declare_parameter('replan_threshold', 0.3)
        self.declare_parameter('retry_limit', 3)
        self.declare_parameter('max_goal_dist', 5.0)

        self.stop_offset = float(self.get_parameter('stop_offset').value)
        self.arrive_slack = float(self.get_parameter('arrive_slack').value)
        self.replan_threshold = float(self.get_parameter('replan_threshold').value)
        self.retry_limit = int(self.get_parameter('retry_limit').value)
        self.max_goal_dist = float(self.get_parameter('max_goal_dist').value)

        self.state = 'IDLE'          # IDLE / PENDING / NAVIGATING / ARRIVED
        self.goal_handle = None
        self.current_goal_xy = None
        self.latest_target = None
        self.replans = 0
        self.retries = 0

        self.create_subscription(PoseStamped, '/ugv_auto/target_pose', self.target_cb, 10)
        self.client = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.pub_cmd = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_status = self.create_publisher(String, '/ugv_auto/status', 10)

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.timer = self.create_timer(0.5, self.tick)
        self.get_logger().info('approach_manager 已启动，等待目标...')

    # ------------------------------------------------------------------ 目标回调（只记录，不阻塞）
    def target_cb(self, msg):
        self.latest_target = msg
        if self.state == 'IDLE':
            self.state = 'PENDING'
        elif self.state == 'NAVIGATING' and self.current_goal_xy is not None:
            dx = msg.pose.position.x - self.current_goal_xy[0]
            dy = msg.pose.position.y - self.current_goal_xy[1]
            if math.hypot(dx, dy) > self.replan_threshold and self.replans < self.retry_limit:
                self.get_logger().info(f'目标移动 {math.hypot(dx, dy):.2f} m，取消并重规划')
                self.replans += 1
                if self.goal_handle is not None:
                    self.goal_handle.cancel_goal_async()
                self.state = 'PENDING'

    # ------------------------------------------------------------------ 定时器：非阻塞发送
    def tick(self):
        if self.state != 'PENDING' or self.latest_target is None:
            return
        if not self.client.server_is_ready():
            return  # Nav2 尚未就绪，下一轮再试
        self._do_send(self.latest_target)

    def _base_xy(self):
        try:
            tf = self.tf_buffer.lookup_transform(
                'map', 'base_footprint', rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.5))
            return tf.transform.translation.x, tf.transform.translation.y
        except Exception:
            return None, None

    def _do_send(self, target):
        bx, by = self._base_xy()
        tx, ty = target.pose.position.x, target.pose.position.y
        if bx is None:
            self.get_logger().warn('无法获取机器人位姿，等待下一轮')
            return
        dist = math.hypot(tx - bx, ty - by)
        if dist > self.max_goal_dist:
            self.get_logger().warn(f'目标距离 {dist:.2f} m 超过上限，忽略')
            self.state = 'IDLE'
            return
        if dist <= self.stop_offset + self.arrive_slack:
            self.state = 'ARRIVED'
            self.set_status(f'ARRIVED: 距离目标仅 {dist:.2f} m，无需移动')
            self.get_logger().info(f'已在目标跟前（{dist:.2f} m），判定到达')
            return

        ux, uy = (tx - bx) / dist, (ty - by) / dist
        gx, gy = tx - ux * self.stop_offset, ty - uy * self.stop_offset
        yaw = math.atan2(ty - by, tx - bx)

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = gx
        goal.pose.pose.position.y = gy
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self.get_logger().info(f'发送导航目标: ({gx:.2f}, {gy:.2f})，目标距离 {dist:.2f} m')
        fut = self.client.send_goal_async(goal)
        fut.add_done_callback(self._on_response)
        self.current_goal_xy = (gx, gy)

    def _on_response(self, fut):
        gh = None
        try:
            gh = fut.result()
        except Exception as e:
            self.get_logger().error(f'发送目标异常: {e}')
        if gh is None or not gh.accepted:
            self.get_logger().error('目标被拒绝')
            self._retry_or_fail()
            return
        self.goal_handle = gh
        self.state = 'NAVIGATING'
        self.set_status(f'NAVIGATING -> ({self.current_goal_xy[0]:.2f}, '
                        f'{self.current_goal_xy[1]:.2f})')
        gh.get_result_async().add_done_callback(self._on_done)

    def _on_done(self, fut):
        try:
            status = fut.result().status
        except Exception as e:
            self.get_logger().error(f'获取结果异常: {e}')
            status = GoalStatus.STATUS_UNKNOWN
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.state = 'ARRIVED'
            self.set_status('ARRIVED: 已到达目标附近，任务完成')
            self.get_logger().info('已到达目标附近，任务完成')
        else:
            self.get_logger().warn(f'导航结束，状态码 {status}')
            self._retry_or_fail()

    def _retry_or_fail(self):
        self.retries += 1
        if self.latest_target is not None and self.retries <= self.retry_limit:
            self.get_logger().info(f'用最新目标重试({self.retries}/{self.retry_limit})')
            self.state = 'PENDING'
        else:
            self.set_status('FAILED: 多次尝试未成功，回到 IDLE 等待新目标')
            self.get_logger().error('任务失败，等待新目标')
            self.state = 'IDLE'
            self.retries = 0
            self.replans = 0

    def set_status(self, s):
        self.pub_status.publish(String(data=f'{self.state}: {s}'))

    # ------------------------------------------------------------------ 安全退出
    def stop(self):
        if self.goal_handle is not None:
            try:
                self.goal_handle.cancel_goal_async()
            except Exception:
                pass
        zero = Twist()
        for _ in range(5):
            self.pub_cmd.publish(zero)

    def destroy_node(self):
        self.stop()
        return super().destroy_node()


def main():
    rclpy.init()
    node = ApproachManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.stop()
    node.destroy_node()
    rclpy.shutdown()
