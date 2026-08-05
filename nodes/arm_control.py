"""机械臂控制节点 - 真实机械臂控制 (FollowJointTrajectoryAction)

输入:
  arm_cmd   {"item": str, "index": int}   抓取指令
输出:
  arm_done  {"success": bool, "item": str, "index": int, "elapsed": float, "error": str|None}

控制接口 (servo_manager 提供):
  /arm_controller/follow_joint_trajectory    机械臂 5 关节 action (joint1..joint5)
  /gripper_controller/follow_joint_trajectory 夹爪/腕 action (r_joint, 舵机ID 10)

示教点位 (必须现场标定):
  读取 config/arm_poses.json (相对本文件 ../config/arm_poses.json):
    {
      "home":        [j1..j5],          # 初始收拢位
      "pre_grasp":   [j1..j5],          # 物品上方预抓取位
      "grasp":       [j1..j5],          # 抓取位(下降到位)
      "lift":        [j1..j5],          # 抓起后抬起位
      "drop":        [j1..j5],          # 包上方放置位
      "gripper_open":  float,           # 夹爪张开位置
      "gripper_close": float,           # 夹爪闭合位置
      "joint_names": ["joint1", ..., "joint5"]
    }
  现场用 nodes/arm_teach.py 示教生成此文件。

抓取流程: home -> pre_grasp -> (夹爪开) -> grasp -> 夹爪闭 -> lift -> drop -> 夹爪开 -> home
"""
import json
import os
import time
import traceback

import pyarrow as pa
from dora import Node

node = Node()

# ---- 点位配置 ----
_POSES_FILE = os.environ.get(
    "ARM_POSES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "arm_poses.json"),
)
ARM_MOVE_TIMEOUT = float(os.environ.get("ARM_MOVE_TIMEOUT", "8"))   # 单段轨迹超时 s
ARM_TRAJ_DURATION = float(os.environ.get("ARM_TRAJ_DURATION", "1.5"))  # 单段轨迹时长 s


def _ensure_ros_init():
    import rospy
    if not rospy.core.is_initialized():
        rospy.init_node("arm_control", anonymous=True)
    return rospy


_rospy = _ensure_ros_init()
import actionlib
from control_msgs.msg import FollowJointTrajectoryGoal
from trajectory_msgs.msg import JointTrajectoryPoint


def _load_poses():
    try:
        with open(_POSES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[arm_control] 读取点位失败: {e}", flush=True)
        return {}


def _norm_pose(pose, joint_names):
    """把点位归一化为 dict {joint_name: value}, 缺失关节补 0。"""
    if isinstance(pose, dict):
        return {j: float(pose.get(j, 0.0)) for j in joint_names}
    # 数组形式按 joint_names 顺序对齐
    return {j: float(pose[i]) if i < len(pose) else 0.0 for i, j in enumerate(joint_names)}


def _wait_result(client, timeout_s):
    """等待 action 结果, 返回 (succeeded, error_str)。"""
    if client.wait_for_result(_rospy.Duration(timeout_s)):
        state = client.get_state()
        if state == actionlib.GoalStatus.SUCCEEDED:
            return True, None
        return False, f"goal state={state}"
    client.cancel_goal()
    return False, "timeout"


def _send_trajectory(client, joint_names, positions, duration):
    """发送一条关节轨迹, 返回 (ok, err)。"""
    goal = FollowJointTrajectoryGoal()
    goal.trajectory.joint_names = list(joint_names)
    point = JointTrajectoryPoint()
    point.positions = [float(p) for p in positions]
    point.time_from_start = _rospy.Duration(duration)
    goal.trajectory.points = [point]
    client.send_goal(goal)
    return _wait_result(client, ARM_MOVE_TIMEOUT + duration + 1.0)


class Arm:
    """机械臂控制句柄 (惰性初始化 action clients)。"""

    def __init__(self, poses):
        rospy = _ensure_ros_init()
        import actionlib
        from control_msgs.msg import FollowJointTrajectoryAction
        from trajectory_msgs.msg import JointTrajectoryPoint
        self.rospy = rospy
        self.JointTrajectoryPoint = JointTrajectoryPoint
        self.poses = poses
        self.joint_names = poses.get(
            "joint_names", ["joint1", "joint2", "joint3", "joint4", "joint5"])
        self._arm_client = None
        self._grip_client = None
        self._grip_names = ["r_joint"]
        self.arm_client = actionlib.SimpleActionClient(
            "/arm_controller/follow_joint_trajectory", FollowJointTrajectoryAction)
        self.grip_client = actionlib.SimpleActionClient(
            "/gripper_controller/follow_joint_trajectory", FollowJointTrajectoryAction)
        print(f"[arm_control] 机械臂关节: {self.joint_names}, 夹爪: {self.grip_names}", flush=True)
        if not self.arm_client.wait_for_server(rospy.Duration(5)):
            raise RuntimeError("arm action server 不可用")
        if not self.grip_client.wait_for_server(rospy.Duration(5)):
            raise RuntimeError("gripper action server 不可用")
        print("[arm_control] action server 连接成功", flush=True)

    def move_arm(self, pose, duration=None):
        """移动到指定关节位。pose 为 dict 或 list。"""
        target = _norm_pose(pose, self.joint_names)
        positions = [target[j] for j in self.joint_names]
        return _send_trajectory(
            self.arm_client, self.joint_names, positions,
            duration or ARM_TRAJ_DURATION)

    def move_gripper(self, pos, duration=0.8):
        return _send_trajectory(self.grip_client, self.grip_names, [float(pos)], duration)

    def go_home(self):
        return self.move_arm(self.poses.get("home", [0.0] * len(self.joint_names)))

    def grab(self, item):
        """执行 取物->放置 全流程, 返回 (success, error)。"""
        poses = self.poses
        names = self.joint_names
        gripper_open = float(poses.get("gripper_open", 0.0))
        gripper_close = float(poses.get("gripper_close", 0.5))

        def step(name, func, *args):
            print(f"[arm_control]   阶段: {name}", flush=True)
            ok, err = func(*args)
            if not ok:
                raise RuntimeError(f"{name} 失败: {err}")
            return ok

        # 1. 回初始位
        step("回初始位", self.go_home)
        # 2. 到预抓取位, 夹爪预先张开
        step("到预抓取位", self.move_arm, poses.get("pre_grasp", poses.get("home", [0] * len(names))))
        step("夹爪张开", self.move_gripper, gripper_open)
        # 3. 下降抓取
        step("下降到抓取位", self.move_arm, poses.get("grasp", poses.get("pre_grasp", [0] * len(names))))
        # 4. 闭合夹爪
        step("闭合夹爪", self.move_gripper, gripper_close)
        # 5. 抬起
        step("抬起物品", self.move_arm, poses.get("lift", poses.get("grasp", [0] * len(names))))
        # 6. 移动到包上方
        step("移动到包上方", self.move_arm, poses.get("drop", poses.get("lift", [0] * len(names))))
        # 7. 松开夹爪放入包中
        step("松开夹爪", self.move_gripper, gripper_open)
        # 8. 回初始位
        step("回初始位", self.go_home)
        return True, None


print("[arm_control] 机械臂节点启动 (真实控制: FollowJointTrajectoryAction)", flush=True)

_poses = _load_poses()
if not _poses:
    print("[arm_control] 警告: 未找到示教点位配置, 抓取将使用全零位姿", flush=True)
_state = {"arm": None, "error": None}  # 惰性初始化句柄 (可变容器, 免 global)


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "arm_cmd":
        continue

    try:
        if event["value"] is None:
            raise ValueError("empty value")
        cmd = json.loads(event["value"].to_pylist()[0])
        item = cmd["item"]
        index = cmd.get("index", -1)
    except Exception as e:
        print(f"[arm_control] 无效 arm_cmd 已忽略: {e}", flush=True)
        node.send_output("arm_done", pa.array([json.dumps(
            {"success": False, "item": None, "index": -1,
             "error": f"invalid arm_cmd: {e}"}, ensure_ascii=False)]))
        continue

    print(f"[arm_control] 收到抓取指令: {item} (序号 {index})", flush=True)
    t0 = time.monotonic()
    result = {"success": False, "item": item, "index": index, "elapsed": None, "error": None}
    try:
        # 惰性初始化 (首次调用才连 action server, 启动时板子可能未就绪)
        if _state["arm"] is None:
            _state["arm"] = Arm(_poses)
        ok, err = _state["arm"].grab(item)
        result["success"] = ok
        result["error"] = err
    except Exception as e:
        traceback.print_exc()
        result["error"] = f"{type(e).__name__}: {e}"

    result["elapsed"] = round(time.monotonic() - t0, 2)
    if result["success"]:
        print(f"[arm_control] 已将 {item} 放入包中 (耗时 {result['elapsed']}s)", flush=True)
    else:
        print(f"[arm_control] 抓取失败: {item} ({result['error']})", flush=True)

    node.send_output("arm_done", pa.array([json.dumps(result, ensure_ascii=False)]))
