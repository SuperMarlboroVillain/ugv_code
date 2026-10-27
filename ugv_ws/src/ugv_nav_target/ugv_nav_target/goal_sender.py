"""识别到目标后，通过 Nav2 自动导航到目标位置。

订阅 /target_detector/target_pose（map 系下的目标位置），调用 Nav2 的
NavigateToPose 动作 (bt_navigator) 让机器人自主规划路径并行驶到目标。

特性：
  - 收到目标后自动发送导航动作；
  - 导航过程中目标位置更新超过重规划阈值时自动改去新位置；
  - 提供 /target_detector/reset 服务，可随时取消当前导航任务、重新待命。
"""

import math

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger


class GoalSender(Node):
    def __init__(self):
        super().__init__("goal_sender")

        self.declare_parameter("pose_topic", "/target_detector/target_pose")
        self.declare_parameter("action_name", "/navigate_to_pose")
        self.declare_parameter("replan_move_threshold", 0.3)
        self.declare_parameter("arrive_threshold", 0.35)

        self.replan_threshold = float(self.get_parameter("replan_move_threshold").value)
        self.arrive_threshold = float(self.get_parameter("arrive_threshold").value)

        self.action_client = ActionClient(
            self, NavigateToPose, self.get_parameter("action_name").value
        )
        self.current_goal_handle = None
        self.current_target = None
        self._accepting = True

        self.create_subscription(
            PoseStamped, self.get_parameter("pose_topic").value, self.target_cb, 10
        )
        self.create_service(Trigger, "/target_detector/reset", self.reset_cb)

        self.get_logger().info(
            f"等待目标位置 ({self.get_parameter('pose_topic').value})，"
            f"导航动作: {self.get_parameter('action_name').value}"
        )

    # ------------------------------------------------------------------
    def reset_cb(self, request, response):
        """取消当前导航，重新等待目标。"""
        if self.current_goal_handle is not None:
            self.current_goal_handle.cancel_goal_async()
            self.get_logger().info("已取消当前导航任务，重新待命")
        else:
            self.get_logger().info("当前没有导航任务")
        self.current_target = None
        self._accepting = True
        response.success = True
        response.message = "reset done"
        return response

    # ------------------------------------------------------------------
    def dist2d(self, a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    def target_cb(self, msg):
        if not self._accepting:
            return
        new_target = msg.pose.position

        if self.current_target is not None and self.current_goal_handle is not None:
            moved = self.dist2d(new_target, self.current_target)
            if moved < self.replan_threshold:
                return  # 目标没怎么动，忽略
            self.get_logger().info(f"目标移动了 {moved:.2f} m，重新规划路径")

        self.current_target = new_target
        self.send_goal(msg)

    # ------------------------------------------------------------------
    def send_goal(self, pose_msg):
        if not self.action_client.wait_for_server(timeout_sec=1.0):
            self.get_logger().error("Nav2 动作服务器不可用，请确认 nav.launch.py 已启动")
            return

        goal = NavigateToPose.Goal()
        goal.pose = pose_msg

        self.get_logger().info(
            f"发送导航目标: ({pose_msg.pose.position.x:.2f}, {pose_msg.pose.position.y:.2f})"
        )
        future = self.action_client.send_goal_async(
            goal, feedback_callback=self.feedback_cb
        )
        future.add_done_callback(self.goal_response_cb)

    def goal_response_cb(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn("导航目标被拒绝")
            return
        self.current_goal_handle = goal_handle
        self.get_logger().info("导航目标已被接受，机器人开始移动")

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_cb)

    def feedback_cb(self, feedback_msg):
        fb = feedback_msg.feedback
        remaining = fb.distance_remaining
        if remaining < 1e6:
            self.get_logger().info(f"距离目标还剩 {remaining:.2f} m", once=True)

    def result_cb(self, future):
        status = future.result().status
        self.current_goal_handle = None
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info("已到达目标位置！")
        elif status == GoalStatus.STATUS_CANCELED:
            self.get_logger().info("导航已取消")
        else:
            self.get_logger().warn(f"导航失败/中止，状态码: {status}")


def main():
    rclpy.init()
    node = GoalSender()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
