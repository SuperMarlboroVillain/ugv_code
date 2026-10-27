#!/usr/bin/env python3
"""cmd_vel 安全看门狗：指令断流自动归零。

背景：底盘 base_node/下位机保持最后一条速度指令，没有超时保护；
任何发布者异常死亡都会造成机器人失控。本节点订阅 /cmd_vel，
原样转发到 /cmd_vel_safe；超过 0.5 s 无新指令则持续发布零速。

配合 bringup_lidar.launch.py 中 base_node 的重映射
('/cmd_vel' -> '/cmd_vel_safe') 使用。看门狗自身死亡时
base_node 收不到任何指令，同样停车（fail-safe）。
"""
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

TIMEOUT = 0.5


class CmdVelWatchdog(Node):
    def __init__(self):
        super().__init__('cmd_vel_watchdog')
        self.declare_parameter('timeout', TIMEOUT)
        self.timeout = float(self.get_parameter('timeout').value)
        self.last_msg_t = None
        self.last_twist = Twist()
        self.create_subscription(Twist, '/cmd_vel', self.cb, 10)
        self.pub = self.create_publisher(Twist, '/cmd_vel_safe', 10)
        self.create_timer(0.1, self.tick)
        self.get_logger().info(
            f'cmd_vel 看门狗启动: /cmd_vel -> /cmd_vel_safe, '
            f'超时 {self.timeout}s 自动归零')

    def cb(self, msg):
        self.last_msg_t = self.get_clock().now()
        self.last_twist = msg

    def tick(self):
        tw = Twist()
        if self.last_msg_t is not None:
            age = (self.get_clock().now() - self.last_msg_t).nanoseconds / 1e9
            if age <= self.timeout:
                tw = self.last_twist
        self.pub.publish(tw)


def main():
    rclpy.init()
    node = CmdVelWatchdog()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.pub.publish(Twist())


if __name__ == '__main__':
    main()
