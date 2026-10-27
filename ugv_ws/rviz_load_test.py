#!/usr/bin/env python3
# RViz A/B 压测：模拟导航栈典型数据流（map/双代价地图/雷达/AMCL粒子云/路径/TF）。
# 仅用于对比 RViz 配置内存占用，数据是假的。
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import OccupancyGrid, Path
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import PoseArray, PoseStamped, TransformStamped
from tf2_msgs.msg import TFMessage


class FakeNavLoad(Node):
    def __init__(self):
        super().__init__('rviz_load_test')
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        best_effort = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.map_pub = self.create_publisher(OccupancyGrid, '/map', latched)
        self.gc_pub = self.create_publisher(OccupancyGrid, '/global_costmap/costmap', latched)
        self.lc_pub = self.create_publisher(OccupancyGrid, '/local_costmap/costmap', latched)
        self.scan_pub = self.create_publisher(LaserScan, '/scan', best_effort)
        self.pcl_pub = self.create_publisher(PoseArray, '/particle_cloud', best_effort)
        self.plan_pub = self.create_publisher(Path, '/plan', best_effort)
        self.lplan_pub = self.create_publisher(Path, '/local_plan', best_effort)
        self.tf_pub = self.create_publisher(TFMessage, '/tf', 10)
        self.t = 0.0
        self.timer = self.create_timer(0.05, self.tick)  # 20Hz 总节拍

    def make_grid(self, w, h, seed):
        g = OccupancyGrid()
        g.header.frame_id = 'map'
        g.info.resolution = 0.05
        g.info.width = w
        g.info.height = h
        g.data = [(i * 7 + seed) % 100 for i in range(w * h)]
        return g

    def tick(self):
        self.t += 0.05
        now = self.get_clock().now().to_msg()
        if int(self.t * 20) % 40 == 0:  # 0.5Hz 地图/代价地图
            m = self.make_grid(551, 395, 3); m.header.stamp = now; self.map_pub.publish(m)
            g = self.make_grid(551, 395, 11); g.header.stamp = now; self.gc_pub.publish(g)
            l = self.make_grid(100, 100, 23); l.header.stamp = now; self.lc_pub.publish(l)
        if int(self.t * 20) % 4 == 0:  # 5Hz 雷达
            s = LaserScan()
            s.header.frame_id = 'base_lidar_link'
            s.header.stamp = now
            s.angle_min, s.angle_max, s.angle_increment = -math.pi, math.pi, math.pi / 225
            s.range_min, s.range_max = 0.1, 8.0
            s.ranges = [3.0 + math.sin(i * 0.1 + self.t) for i in range(451)]
            self.scan_pub.publish(s)
        if int(self.t * 20) % 10 == 0:  # 2Hz 粒子云(2000) + 路径
            pa = PoseArray()
            pa.header.frame_id = 'map'
            pa.header.stamp = now
            for i in range(2000):
                p = PoseStamped().pose
                p.position.x = 2.0 + 0.5 * math.cos(i * 0.003 + self.t)
                p.position.y = 2.0 + 0.5 * math.sin(i * 0.003 + self.t)
                pa.poses.append(p)
            self.pcl_pub.publish(pa)
            path = Path()
            path.header.frame_id = 'map'
            path.header.stamp = now
            for i in range(60):
                p = PoseStamped()
                p.pose.position.x = i * 0.05
                p.pose.position.y = math.sin(i * 0.1)
                path.poses.append(p)
            self.plan_pub.publish(path)
            self.lplan_pub.publish(path)
        if int(self.t * 20) % 2 == 0:  # 10Hz TF 链
            tf = TFMessage()
            for parent, child, x in (('map', 'odom', 0.1), ('odom', 'base_footprint', 0.0),
                                     ('base_footprint', 'base_lidar_link', 0.2)):
                ts = TransformStamped()
                ts.header.frame_id = parent
                ts.header.stamp = now
                ts.child_frame_id = child
                ts.transform.translation.x = x
                ts.transform.rotation.w = 1.0
                tf.transforms.append(ts)
            self.tf_pub.publish(tf)


rclpy.init()
rclpy.spin(FakeNavLoad())
