#!/usr/bin/env python3
"""键盘遥控节点（无手柄场景，需交互式终端）。

按键（teleop_twist_keyboard 风格）：
  i 前进    k/空格 停止    , 后退
  j 左转    l 右转
  u/o 前左/前右弧线   m/. 后左/后右弧线
  1/2/3 限速档（0.15 / 0.30 / 0.50 m/s）
  [ / ] 直行跑偏微调（左/右，步进 0.01 rad/s，仅前进/后退时生效）
  h 开关航向保持（默认开；反馈优先 /odom 编码器，IMU 兜底）
  q 退出

松开按键 0.6 s 自动归零（防失联乱跑）。终端断流（EOF）时指令清零并
自动退出。必须在前台终端运行：
  ros2 run ugv_auto keyboard_teleop
"""
import select
import sys
import termios
import tty

import math

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu

GEARS = {1: 0.15, 2: 0.30, 3: 0.50}
YAW = 1.0
TRIM_STEP = 0.01
TRIM_MAX = 0.30
HOLD_KP = 1.5          # 航向保持比例增益
HOLD_KI = 0.4          # 航向保持积分增益（对付恒定偏置）
HOLD_MAX = 0.6         # 修正角速度上限 rad/s
I_MAX = 0.3            # 积分项上限
LIN_RAMP = 0.4         # 起步加速度上限 m/s^2
LIN_BRAKE = 1.0        # 减速/倒车加速度上限 m/s^2

BINDINGS = {
    'i': (1.0, 0.0), ',': (-1.0, 0.0),
    'j': (0.0, 1.0), 'l': (0.0, -1.0),
    'u': (1.0, 1.0), 'o': (1.0, -1.0),
    'm': (-1.0, 1.0), '.': (-1.0, -1.0),
    'k': (0.0, 0.0), ' ': (0.0, 0.0),
}


class KeyboardTeleop(Node):
    def __init__(self):
        super().__init__('keyboard_teleop')
        self.declare_parameter('timeout', 0.6)
        self.timeout = float(self.get_parameter('timeout').value)
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(Imu, '/imu/data', self.imu_cb, 10)
        self.yaw = None          # 兼容旧引用，hold 实际用 hold_feedback()
        self.odom_yaw = None
        self.imu_yaw = None
        self.last_odom_t = None
        self.last_imu_t = None
        self.hold_src = None
        self.hold_on = True      # h 键切换航向保持
        self.hold_target = None
        self.hold_i = 0.0
        self.last_hold_t = None
        self.gear = 1
        self.move = (0.0, 0.0)
        self.prev_move = (0.0, 0.0)
        self.trim = 0.0
        self.cur_lin = 0.0
        self.eof_n = 0
        self.last_key_t = self.get_clock().now()
        self.create_timer(0.1, self.tick)
        self.get_logger().info(
            '键盘遥控已启动: i/,/j/l 移动  k/空格 停止  1/2/3 限速  '
            '[/] 跑偏微调(基准)  h 航向保持开关  q 退出  '
            '直行带航向保持(优先编码器/odom 反馈, IMU 兜底)')

    @staticmethod
    def _yaw(q):
        return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                          1.0 - 2.0 * (q.y * q.y + q.z * q.z))

    def imu_cb(self, msg):
        q = msg.orientation
        if q.w != 0.0 or q.z != 0.0:
            self.imu_yaw = self._yaw(q)
            self.last_imu_t = self.get_clock().now()

    def odom_cb(self, msg):
        self.odom_yaw = self._yaw(msg.pose.pose.orientation)
        self.last_odom_t = self.get_clock().now()

    def hold_feedback(self):
        """选航向保持的反馈源：优先 /odom（编码器，实测静止 12s 漂移仅 0.08°）；
        /imu/data（互补滤波）实测 12s 漂 ~1° 且受电机干扰，仅作兜底。"""
        now = self.get_clock().now()
        if self.odom_yaw is not None and \
                (now - self.last_odom_t).nanoseconds / 1e9 <= 0.5:
            return self.odom_yaw, 'odom'
        if self.imu_yaw is not None and \
                (now - self.last_imu_t).nanoseconds / 1e9 <= 0.5:
            return self.imu_yaw, 'imu'
        return None, None

    def quit(self):
        # 在回调内直接 rclpy.shutdown() 会让 spin 卡死，
        # 改抛 KeyboardInterrupt 由 main 的 finally 收尾
        self.pub.publish(Twist())
        raise KeyboardInterrupt

    def tick(self):
        # 交互式终端按键读取
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            ch = sys.stdin.read(1)
            if ch == '':
                # 终端 EOF（窗口关闭/会话断开）：旧状态不得保持，立即清零并退出
                self.eof_n += 1
                self.move = (0.0, 0.0)
                self.last_key_t = self.get_clock().now()
                if self.eof_n == 1:
                    self.get_logger().warn(
                        'stdin 已断开（EOF），指令清零；1.5s 后节点自动退出')
                if self.eof_n > 15:
                    self.quit()
            else:
                self.eof_n = 0
                self.last_key_t = self.get_clock().now()
                if ch == 'q':
                    self.quit()
                elif ch in ('1', '2', '3'):
                    self.gear = int(ch)
                    self.get_logger().info(f'限速档 {self.gear}: '
                                           f'{GEARS[self.gear]} m/s')
                elif ch == '[':
                    self.trim = max(-TRIM_MAX, self.trim - TRIM_STEP)
                    self.get_logger().info(f'跑偏微调: {self.trim:+.2f} rad/s')
                elif ch == ']':
                    self.trim = min(TRIM_MAX, self.trim + TRIM_STEP)
                    self.get_logger().info(f'跑偏微调: {self.trim:+.2f} rad/s')
                elif ch == 'h':
                    self.hold_on = not self.hold_on
                    self.get_logger().info(
                        f'航向保持: {"开" if self.hold_on else "关"}')
                elif ch in BINDINGS:
                    self.move = BINDINGS[ch]

        tw = Twist()
        idle = (self.get_clock().now() - self.last_key_t).nanoseconds / 1e9
        if idle <= self.timeout and self.move != (0.0, 0.0):
            target = self.move[0] * GEARS[self.gear]
            # 起步/换向速度斜坡：减小电机死区不对称的冲击，
            # 也给航向保持闭环在低速度下纠偏的时间
            if target > self.cur_lin:
                self.cur_lin = min(target, self.cur_lin + LIN_RAMP * 0.1)
            else:
                self.cur_lin = max(target, self.cur_lin - LIN_BRAKE * 0.1)
            tw.linear.x = self.cur_lin
            tw.angular.z = self.move[1] * YAW
            if self.move[0] != 0.0:
                tw.angular.z += self.trim
            # 直行/倒退（无人工转向输入）时做航向保持闭环：
            # 起步瞬间锁定当前朝向，反馈优先 /odom（编码器），IMU 兜底；
            # PI 修正补偿电机启停不对称与恒定偏置。
            straight = (self.move[0] != 0.0 and self.move[1] == 0.0)
            fb_yaw, fb_src = (self.hold_feedback()
                              if (straight and self.hold_on) else (None, None))
            if fb_yaw is not None:
                just_started = not (self.prev_move[0] != 0.0
                                    and self.prev_move[1] == 0.0)
                if just_started or self.hold_target is None:
                    self.hold_target = fb_yaw
                    self.hold_i = 0.0
                    self.last_hold_t = self.get_clock().now()
                    self.get_logger().info(f'航向保持锁定（反馈: {fb_src}）')
                now = self.get_clock().now()
                dt = 0.1 if self.last_hold_t is None else max(
                    0.01, (now - self.last_hold_t).nanoseconds / 1e9)
                self.last_hold_t = now
                err = self.hold_target - fb_yaw
                while err > math.pi:
                    err -= 2 * math.pi
                while err < -math.pi:
                    err += 2 * math.pi
                self.hold_i = max(-I_MAX, min(I_MAX,
                                              self.hold_i + HOLD_KI * err * dt))
                ang = self.trim + HOLD_KP * err + self.hold_i
                tw.angular.z = max(-HOLD_MAX, min(HOLD_MAX, ang))
            if not straight or not self.hold_on:
                self.hold_target = None
                self.hold_i = 0.0
        self.prev_move = self.move
        self.pub.publish(tw)


def main():
    rclpy.init()
    node = KeyboardTeleop()
    old = termios.tcgetattr(sys.stdin)
    tty.setraw(sys.stdin.fileno())
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        node.pub.publish(Twist())
        print('\n已退出，发送零速。')


if __name__ == '__main__':
    main()
