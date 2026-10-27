#!/usr/bin/env python3
"""自动建图驾驶节点（无手柄场景）。

低速直线行驶，前方障碍时倒退-转向-继续前进（偏向空间大的一侧），
带急停（全向 0.22 m）、卡死自救（6 s 位移 < 4 cm 强制转向）与
定时结束。配合 Cartographer 使用。

用法（容器内）：
  python3 /home/ws/ugv_ws/src/ugv_auto/scripts/auto_map.py [--max-time 420]
"""
import math

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


def sector_min(ranges, angle_min, inc, lo, hi):
    """求角度区间 [lo,hi]（rad，已归一化到 -pi..pi）内的最小有效距离。"""
    best = float('inf')
    n = len(ranges)
    for i, r in enumerate(ranges):
        if math.isnan(r) or r <= 0.01:
            continue
        a = angle_min + i * inc
        while a > math.pi:
            a -= 2 * math.pi
        while a < -math.pi:
            a += 2 * math.pi
        if lo <= a <= hi and r < best:
            best = r
    return best


class AutoMap(Node):
    def __init__(self):
        super().__init__('auto_map')
        self.declare_parameter('max_time', 420.0)
        self.declare_parameter('speed', 0.15)
        self.declare_parameter('yaw_speed', 0.5)
        self.declare_parameter('front_clear', 0.50)
        self.declare_parameter('emergency_dist', 0.22)
        self.max_time = float(self.get_parameter('max_time').value)
        self.speed = float(self.get_parameter('speed').value)
        self.yaw = float(self.get_parameter('yaw_speed').value)
        self.front_clear = float(self.get_parameter('front_clear').value)
        self.emerg = float(self.get_parameter('emergency_dist').value)

        self.scan = None
        self.scan_time = self.get_clock().now()
        self.last_pos = None
        self.odom_dist = 0.0
        self.state = 'DRIVE'
        self.state_t = self.get_clock().now()
        self.stuck_ref = None
        self.stuck_t = self.get_clock().now()
        self.start = self.get_clock().now()
        self.turn_dir = 1.0

        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_timer(0.1, self.tick)
        self.get_logger().info(
            f'auto_map 启动: speed={self.speed} max_time={self.max_time}s')

    def scan_cb(self, msg):
        self.scan = msg
        self.scan_time = self.get_clock().now()

    def odom_cb(self, msg):
        p = msg.pose.pose.position
        if self.last_pos is not None:
            dx = p.x - self.last_pos[0]
            dy = p.y - self.last_pos[1]
            d = math.hypot(dx, dy)
            if d < 0.3:  # 跳变保护
                self.odom_dist += d
        self.last_pos = (p.x, p.y)

    def set_state(self, s):
        if s != self.state:
            self.state = s
            self.state_t = self.get_clock().now()
            self.get_logger().info(f'状态 -> {s} 里程计累计 {self.odom_dist:.2f} m')

    def tick(self):
        now = self.get_clock().now()
        elapsed = (now - self.start).nanoseconds / 1e9
        if elapsed > self.max_time:
            self.pub.publish(Twist())
            self.get_logger().info(
                f'建图驾驶结束: 用时 {elapsed:.0f}s 里程 {self.odom_dist:.2f} m '
                f'终点 ({self.last_pos[0]:.2f},{self.last_pos[1]:.2f})')
            # 不在回调里 rclpy.shutdown()（会卡死 spin 导致底盘保持最后指令），
            # 改抛 KeyboardInterrupt 由 main 的 finally 收尾发零速
            raise KeyboardInterrupt

        tw = Twist()
        # 雷达看门狗：数据过期立即停车
        if self.scan is None or (now - self.scan_time).nanoseconds / 1e9 > 1.0:
            self.pub.publish(tw)
            return

        msg = self.scan
        front = sector_min(msg.ranges, msg.angle_min, msg.angle_increment,
                           -1.05, 1.05)
        left = sector_min(msg.ranges, msg.angle_min, msg.angle_increment,
                          1.05, 2.10)
        right = sector_min(msg.ranges, msg.angle_min, msg.angle_increment,
                           -2.10, -1.05)
        rear = min(
            sector_min(msg.ranges, msg.angle_min, msg.angle_increment,
                       2.60, 3.70),
            sector_min(msg.ranges, msg.angle_min, msg.angle_increment,
                       -3.70, -2.60))
        full = min(front, left, right)

        # 急停：任何方向过近
        if full < self.emerg and self.state != 'BACK':
            self.set_state('BACK')
            self.turn_dir = 1.0 if left >= right else -1.0

        t_in_state = (now - self.state_t).nanoseconds / 1e9

        # 全状态卡死检测：7 s 位移不足 5 cm 说明顶死/打滑，强制换向转向
        if self.state in ('DRIVE', 'BACK', 'TURN'):
            if self.stuck_ref is None:
                self.stuck_ref = self.last_pos
                self.stuck_t = now
            elif (now - self.stuck_t).nanoseconds / 1e9 > 7.0:
                d = math.hypot(self.last_pos[0] - self.stuck_ref[0],
                               self.last_pos[1] - self.stuck_ref[1])
                if d < 0.05:
                    self.get_logger().warn('卡死，强制反向转向')
                    self.turn_dir = -self.turn_dir
                    self.set_state('TURN')
                self.stuck_ref = self.last_pos
                self.stuck_t = now

        if self.state == 'DRIVE':
            tw.linear.x = self.speed
            if front < self.front_clear:
                self.turn_dir = 1.0 if left >= right else -1.0
                # 倒车前必须确认后方有空间，否则直接原地转向
                if rear > 0.35:
                    self.set_state('BACK')
                else:
                    self.set_state('TURN')
        elif self.state == 'BACK':
            # 倒车中后方被堵：立即停止后退，转入转向
            if rear < 0.25:
                self.set_state('TURN')
            else:
                tw.linear.x = -0.10
                if t_in_state > 1.0:
                    self.set_state('TURN')
        elif self.state == 'TURN':
            tw.angular.z = self.yaw * self.turn_dir
            if front > 0.85 or t_in_state > 6.0:
                self.set_state('DRIVE')

        self.pub.publish(tw)


def main():
    rclpy.init()
    node = AutoMap()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # 连续发零速，确保底盘收到停止指令
        for _ in range(5):
            node.pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.1)


if __name__ == '__main__':
    main()
