#!/usr/bin/env python3
"""通用游戏柄遥控节点（替代 vendor joy_ctrl，任意手柄即插即用）。

订阅标准 /joy（sensor_msgs/Joy），发布 cmd_vel：
- 默认左摇杆：axes[1] 前后线速度，axes[2] 左右角速度（轴号可参数化）
- 死区过滤、限速、按键换挡（可选）、松开自动归零
不依赖 pygame，不依赖特定手柄型号；未检测到手柄时 /joy 无数据，车保持停止。
"""
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import Bool


class JoyTeleop(Node):
    def __init__(self):
        super().__init__('joy_teleop')
        self.declare_parameter('axis_linear', 1)
        self.declare_parameter('axis_angular', 2)
        self.declare_parameter('deadzone', 0.1)
        self.declare_parameter('xspeed_limit', 0.5)
        self.declare_parameter('angular_speed_limit', 1.0)
        self.declare_parameter('gear_steps', [0.4, 0.7, 1.0])
        self.declare_parameter('gear_up_button', 5)    # RB
        self.declare_parameter('gear_down_button', 4)  # LB

        self.axis_linear = int(self.get_parameter('axis_linear').value)
        self.axis_angular = int(self.get_parameter('axis_angular').value)
        self.deadzone = float(self.get_parameter('deadzone').value)
        self.xlimit = float(self.get_parameter('xspeed_limit').value)
        self.zlimit = float(self.get_parameter('angular_speed_limit').value)
        self.gear_steps = list(self.get_parameter('gear_steps').value)
        self.btn_up = int(self.get_parameter('gear_up_button').value)
        self.btn_down = int(self.get_parameter('gear_down_button').value)

        self.gear = 1
        self._prev_up = False
        self._prev_down = False
        self._last_axes = None

        self.pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.pub_state = self.create_publisher(Bool, 'JoyState', 10)
        self.create_subscription(Joy, 'joy', self.cb, 10)
        # 看门狗：0.5 s 无手柄数据自动归零（防止手柄断开时车继续走）
        self.timer = self.create_timer(0.5, self.watchdog)
        self.get_logger().info('joy_teleop 已启动，等待手柄输入...')

    def _dz(self, v):
        return 0.0 if abs(v) < self.deadzone else v

    def cb(self, msg):
        self._last_axes = msg.axes
        if self.btn_up < len(msg.buttons) and msg.buttons[self.btn_up] == 1 \
                and not self._prev_up:
            self.gear = min(self.gear + 1, len(self.gear_steps) - 1)
            self.get_logger().info(f'换挡: {self.gear + 1} 档')
        if self.btn_down < len(msg.buttons) and msg.buttons[self.btn_down] == 1 \
                and not self._prev_down:
            self.gear = max(self.gear - 1, 0)
            self.get_logger().info(f'换挡: {self.gear + 1} 档')
        self._prev_up = self.btn_up < len(msg.buttons) and msg.buttons[self.btn_up] == 1
        self._prev_down = self.btn_down < len(msg.buttons) and msg.buttons[self.btn_down] == 1

        tw = Twist()
        if self.axis_linear < len(msg.axes):
            tw.linear.x = self._dz(msg.axes[self.axis_linear]) \
                * self.xlimit * self.gear_steps[self.gear]
        if self.axis_angular < len(msg.axes):
            tw.angular.z = self._dz(msg.axes[self.axis_angular]) \
                * self.zlimit * self.gear_steps[self.gear]
        self.pub.publish(tw)
        self.pub_state.publish(Bool(data=True))

    def watchdog(self):
        # 手柄失联保护：无新数据时持续发零速
        self.pub.publish(Twist())


def main():
    rclpy.init()
    node = JoyTeleop()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.pub.publish(Twist())
    node.destroy_node()
    rclpy.shutdown()
