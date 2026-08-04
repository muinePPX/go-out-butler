"""导航控制节点 - Layer 0 打印 mock 日志

现场接入时，替换 navigate() 各阶段为真实底盘控制：
  ROS cmd_vel / 导航栈(move_base/Nav2) / 专用底盘 SDK -> 移动到 waypoint
注意: 真实实现需保持 navigate() 返回格式不变:
  {"success": bool, "waypoint": str, "pose": {"x","y"} | None, "error": str | None}
"""
import json
import math
import os
import time
import traceback

import pyarrow as pa
from dora import Node

node = Node()

# ---- Layer 0 mock 参数 ----
MOCK_PLAN_DELAY = 0.2   # 模拟路径规划耗时(秒)
MOCK_CHECK_DELAY = 0.2  # 模拟到达校验耗时(秒)
MOCK_SPEED = 2.0        # 模拟移动速度(米/秒), 移动耗时按点位距离计算
MOCK_MOVE_MIN, MOCK_MOVE_MAX = 0.4, 1.5  # 移动耗时上下限(秒)
# 环境变量 NAV_MOCK_FAIL=点位名 时该点位强制导航失败, 用于演示/测试失败路径
MOCK_FAIL = os.environ.get("NAV_MOCK_FAIL", "")

# 加载导航点位坐标(可选; 缺失时退化为仅按点名 mock, 不校验点位合法性)
WAYPOINTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "config", "waypoints.json")
try:
    with open(WAYPOINTS_PATH, encoding="utf-8") as f:
        WAYPOINTS = json.load(f)
    print(f"[nav_control] 已加载点位配置: {len(WAYPOINTS)} 个点位", flush=True)
except Exception as e:
    WAYPOINTS = {}
    print(f"[nav_control] 点位配置加载失败({e}), 退化为按点名 mock", flush=True)

current_pose = {"x": 0.0, "y": 0.0}  # mock 当前位置, 初始在门口(point_door)

print("[nav_control] 导航节点已启动 (Layer 0: mock)", flush=True)


def navigate(waypoint):
    """Layer 0: 模拟导航全流程。

    现场按阶段替换为真实控制(各阶段注释已标出), 保持返回格式不变:
      成功: {"success": True,  "waypoint": waypoint, "pose": {"x","y"}, "error": None}
      失败: {"success": False, "waypoint": waypoint, "pose": None,      "error": "原因"}
    """
    global current_pose
    result = {"success": False, "waypoint": waypoint, "pose": None, "error": None}

    if not waypoint:
        result["error"] = "点位名为空"
        return result

    # ---- 阶段 1: 解析目标点位坐标 ----
    # 现场替换为: 从地图/点位服务查询目标位姿
    target = WAYPOINTS.get(waypoint)
    if WAYPOINTS and target is None:
        result["error"] = f"未知点位: {waypoint}"
        print(f"[nav_control] [mock]   ! {result['error']}", flush=True)
        return result
    tx, ty = (target["x"], target["y"]) if target else (None, None)

    # ---- 阶段 2: 全局路径规划 ----
    # 现场替换为: 导航栈 make_plan / 全局规划器生成路径
    if tx is not None:
        dist = math.hypot(tx - current_pose["x"], ty - current_pose["y"])
        print(f"[nav_control] [mock]   1. 规划到 {waypoint} ({tx},{ty}) 的路径, "
              f"距离约 {dist:.1f}m", flush=True)
    else:
        dist = None
        print(f"[nav_control] [mock]   1. 规划到 {waypoint} 的路径", flush=True)
    time.sleep(MOCK_PLAN_DELAY)

    # ---- 阶段 3: 底盘移动 ----
    # 现场替换为: 发送导航目标点(action) / cmd_vel 速度控制, 监控状态直到到达
    move_time = min(max((dist or 1.0) / MOCK_SPEED, MOCK_MOVE_MIN), MOCK_MOVE_MAX)
    print(f"[nav_control] [mock]   2. 底盘移动中... (预计 {move_time:.1f}s)", flush=True)
    time.sleep(move_time)

    # Layer 0 模拟导航失败(被阻挡/定位丢失), 真实场景由导航栈状态/超时判断
    if MOCK_FAIL and MOCK_FAIL == waypoint:
        result["error"] = "路径被阻挡, 导航超时(mock 强制失败)"
        print(f"[nav_control] [mock]   ! {result['error']}", flush=True)
        return result

    # ---- 阶段 4: 到达校验 ----
    # 现场替换为: 定位(amcl/odom)确认当前位姿与目标误差在阈值内
    print(f"[nav_control] [mock]   3. 定位校验: 已到达 {waypoint}", flush=True)
    time.sleep(MOCK_CHECK_DELAY)

    if tx is not None:
        current_pose = {"x": tx, "y": ty}
    result["success"] = True
    result["pose"] = dict(current_pose)
    return result


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "nav_cmd":
        continue

    # ---- 解析导航命令; 异常时回复失败应答, 避免调度器在 NAV 状态死等 ----
    try:
        if event["value"] is None:
            raise ValueError("empty value")
        cmd = json.loads(event["value"].to_pylist()[0])
        waypoint = cmd["waypoint"]
        item = cmd.get("item")  # 仅用于日志, 允许缺省
        index = cmd.get("index", -1)
    except Exception as e:
        print(f"[nav_control] 无效 nav_cmd 已忽略: {e}", flush=True)
        node.send_output("nav_done", pa.array([json.dumps(
            {"success": False, "waypoint": None, "item": None, "index": -1,
             "error": f"invalid nav_cmd: {e}"}, ensure_ascii=False)]))
        continue

    print(f"[nav_control] [mock] 收到导航指令: {waypoint} (取 {item}, 序号 {index})", flush=True)

    # ---- 执行导航; 异常兜底(mock 不应抛出, 现场底盘可能断连/导航栈异常) ----
    t0 = time.monotonic()
    try:
        result = navigate(waypoint)
    except Exception as e:
        traceback.print_exc()
        result = {"success": False, "waypoint": waypoint, "pose": None,
                  "error": f"{type(e).__name__}: {e}"}
    elapsed = time.monotonic() - t0

    if result["success"]:
        print(f"[nav_control] [mock] 已到达 {waypoint} (耗时 {elapsed:.1f}s)", flush=True)
    else:
        print(f"[nav_control] [mock] 导航失败: {waypoint} ({result['error']})", flush=True)

    # ---- 上报结果, 回显 index 便于调度器核对 ----
    nav_done = {
        "success": result["success"],
        "waypoint": waypoint,
        "item": item,
        "index": index,
        "pose": result["pose"],
        "elapsed": round(elapsed, 2),
        "error": result["error"],
    }
    node.send_output("nav_done", pa.array([json.dumps(nav_done, ensure_ascii=False)]))
