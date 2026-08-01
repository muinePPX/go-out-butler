"""导航控制节点 - Layer 0 打印 mock 日志

现场接入时，替换 navigate() 为真实底盘控制：
  ROS cmd_vel / 导航栈 / 专用底盘 SDK -> 移动到 waypoint
"""
import json
import time
import pyarrow as pa
from dora import Node

node = Node()
print("[nav_control] 导航节点已启动 (Layer 0: mock)", flush=True)


def navigate(waypoint):
    """Layer 0: 模拟导航。现场替换为真实底盘控制。"""
    time.sleep(1.0)  # 模拟导航耗时
    return True


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "nav_cmd":
        continue

    cmd = json.loads(event["value"].to_pylist()[0])
    waypoint = cmd["waypoint"]
    item = cmd["item"]
    print(f"[nav_control] [mock] 导航到 {waypoint} (取 {item})...", flush=True)

    ok = navigate(waypoint)
    print(f"[nav_control] [mock] {'已到达' if ok else '导航失败'} {waypoint}", flush=True)

    nav_done = {"success": ok, "waypoint": waypoint, "item": item}
    node.send_output("nav_done", pa.array([json.dumps(nav_done, ensure_ascii=False)]))
