#!/usr/bin/env python3
"""静止诊断: 同时采样 /imu/data 与 /odom 的偏航角，评估航向保持反馈源质量。"""
import math
import sys
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry


def yaw_from_q(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Diag(Node):
    def __init__(self, dur):
        super().__init__('teleop_diag')
        self.dur = dur
        self.imu = []
        self.odom = []
        self.create_subscription(Imu, '/imu/data', self.imu_cb, 50)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 50)
        self.create_timer(1.0, self.report)
        self.t0 = self.get_clock().now()

    def imu_cb(self, msg):
        self.imu.append(yaw_from_q(msg.orientation))

    def odom_cb(self, msg):
        self.odom.append(yaw_from_q(msg.pose.pose.orientation))

    @staticmethod
    def _stat(name, xs):
        if not xs:
            print(f'{name}: 无数据!')
            return None
        # 处理角度环绕：逐点差分 unwrap
        u = [xs[0]]
        for a, b in zip(xs, xs[1:]):
            d = b - a
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            u.append(u[-1] + d)
        mean = sum(u) / len(u)
        var = sum((x - mean) ** 2 for x in u) / len(u)
        print(f'{name}: n={len(xs)} 起始={math.degrees(u[0]):8.2f}° '
              f'结尾={math.degrees(u[-1]):8.2f}° 漂移={math.degrees(u[-1]-u[0]):+7.3f}° '
              f'峰峰值={math.degrees(max(u)-min(u)):6.3f}° σ={math.sqrt(var)*1000:7.1f}m°')
        return u[0], u[-1]

    def report(self):
        el = (self.get_clock().now() - self.t0).nanoseconds / 1e9
        print(f'--- 已采样 {el:.0f}s imu={len(self.imu)} odom={len(self.odom)}')
        if el >= self.dur:
            print('====== 结果汇总（机器人应保持静止）======')
            a = self._stat('/imu/data 偏航', self.imu)
            b = self._stat('/odom     偏航', self.odom)
            if a and b:
                off0 = math.degrees(a[0] - b[0])
                off1 = math.degrees(a[1] - b[1])
                print(f'imu-odom 初始偏差={off0:.2f}° 结束偏差={off1:.2f}° '
                      f'差值变化={off1-off0:+.3f}°')
            raise SystemExit(0)  # 在 executor 线程内调 rclpy.shutdown() 会死锁，直接退


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    rclpy.init()
    rclpy.spin(Diag(dur))
    print('诊断结束')


if __name__ == '__main__':
    main()
