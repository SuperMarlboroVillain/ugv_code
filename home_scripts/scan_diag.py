#!/usr/bin/env python3
"""抓一帧 /scan，打印前/左/右扇区最小值与近距离波束分布。"""
import math

import rclpy
from sensor_msgs.msg import LaserScan


def norm(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def main():
    rclpy.init()
    n = rclpy.create_node('scan_diag')
    got = {}

    def cb(m):
        beams = []
        for i, r in enumerate(m.ranges):
            if math.isnan(r) or r <= 0.01:
                continue
            beams.append((norm(m.angle_min + i * m.angle_increment), r))
        got['b'] = beams

    n.create_subscription(LaserScan, '/scan', cb, 1)
    while 'b' not in got:
        rclpy.spin_once(n, timeout_sec=1.0)

    b = got['b']
    front = [r for a, r in b if abs(a) < 1.05]
    left = [r for a, r in b if 1.05 <= a <= 2.10]
    right = [r for a, r in b if -2.10 <= a <= -1.05]
    close = sorted(((round(a, 2), round(r, 2)) for a, r in b if r < 0.6),
                   key=lambda t: t[1])
    print(f'beams={len(b)} front_min={min(front):.2f} '
          f'left_min={min(left):.2f} right_min={min(right):.2f}')
    print(f'beams<0.6m: {len(close)} closest: {close[:20]}')
    n.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
