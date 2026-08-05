"""机械臂示教工具 - 现场标定抓取点位

用法 (板子上):
  run python3 nodes/arm_teach.py            # 实时显示 5 关节 + 夹爪位置
  run python3 nodes/arm_teach.py --save home  # 把当前姿态保存为点位 'home'

操作流程:
  1. 手动(或用控制工具)把机械臂摆到目标姿态
  2. 按提示运行 --save <点位名> 保存当前关节角
  3. 依次保存 home / pre_grasp / grasp / lift / drop 和夹爪开闭位置
  4. 生成/更新 config/arm_poses.json, 供 arm_control.py 使用

点位名: home pre_grasp grasp lift drop | gripper_open gripper_close (夹爪用 --gripper)
"""
import argparse
import json
import os
import sys
import time

import rospy
from control_msgs.msg import FollowJointTrajectoryFeedback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config"))
# 上一行保留仅用于让脚本在任意 cwd 下运行; 真正路径用变量
_POSES_FILE = os.environ.get(
    "ARM_POSES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "arm_poses.json"),
)

VALID_POSES = {"home", "pre_grasp", "grasp", "lift", "drop"}


def main():
    ap = argparse.ArgumentParser(description="机械臂示教工具")
    ap.add_argument("--save", type=str, default=None,
                    help="保存当前姿态为点位名 (home/pre_grasp/grasp/lift/drop)")
    ap.add_argument("--gripper", action="store_true",
                    help="配合 --save 保存夹爪位置 (gripper_open/gripper_close 需自定义名)")
    ap.add_argument("--gripper-pos", type=float, default=None,
                    help="直接保存夹爪位置到 gripper_open/gripper_close (二选一, 需传 --name)")
    ap.add_argument("--name", type=str, default=None, help="gripper-pos 模式下的点位名")
    args = ap.parse_args()

    if not rospy.core.is_initialized():
        rospy.init_node("arm_teach", anonymous=True)

    # ---- 读取当前关节状态 ----
    def read_arm():
        msg = rospy.wait_for_message("/arm_controller/state", FollowJointTrajectoryFeedback, timeout=5)
        return dict(zip(msg.joint_names, msg.desired.positions))

    def read_gripper():
        msg = rospy.wait_for_message("/gripper_controller/state", FollowJointTrajectoryFeedback, timeout=5)
        return dict(zip(msg.joint_names, msg.desired.positions))

    if args.save:
        poses = {}
        if os.path.exists(_POSES_FILE):
            with open(_POSES_FILE, "r", encoding="utf-8") as f:
                poses = json.load(f)
        if args.gripper:
            g = read_gripper()
            val = list(g.values())[0]
            key = args.save
            poses[key] = val
            print(f"夹爪点位 {key} = {val:.3f}")
        else:
            if args.save not in VALID_POSES:
                print(f"警告: 点位名 {args.save} 不在标准集合 {sorted(VALID_POSES)}", file=sys.stderr)
            arm = read_arm()
            order = poses.get("joint_names", ["joint1", "joint2", "joint3", "joint4", "joint5"])
            poses["joint_names"] = order
            poses[args.save] = [arm.get(j, 0.0) for j in order]
            print(f"点位 {args.save} = {[round(v, 3) for v in poses[args.save]]}")
        with open(_POSES_FILE, "w", encoding="utf-8") as f:
            json.dump(poses, f, ensure_ascii=False, indent=2)
        print(f"已保存到 {_POSES_FILE}")
        return

    if args.gripper_pos is not None:
        poses = {}
        if os.path.exists(_POSES_FILE):
            with open(_POSES_FILE, "r", encoding="utf-8") as f:
                poses = json.load(f)
        key = args.name or "gripper_close"
        poses[key] = float(args.gripper_pos)
        with open(_POSES_FILE, "w", encoding="utf-8") as f:
            json.dump(poses, f, ensure_ascii=False, indent=2)
        print(f"夹爪点位 {key} = {args.gripper_pos}, 已保存")
        return

    # ---- 实时显示模式 ----
    print("实时显示机械臂关节 (Ctrl+C 退出):")
    while True:
        try:
            arm = read_arm()
            g = read_gripper()
            arm_str = " ".join(f"{k}={v:+.3f}" for k, v in arm.items())
            grip_str = " ".join(f"{k}={v:+.3f}" for k, v in g.items())
            print(f"\r[臂] {arm_str}  [夹爪] {grip_str}  ", end="", flush=True)
            time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n退出")
            break
        except Exception as e:
            print(f"\r读取失败: {e}    ", end="", flush=True)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
