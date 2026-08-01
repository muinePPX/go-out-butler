"""机械臂控制节点 - Layer 0 打印 mock 日志

现场接入时，替换 grab() 为真实机械臂控制：
  ROS 关节话题 / 机械臂 SDK -> 抓取物品 -> 放入门口包中
"""
import json
import time
import pyarrow as pa
from dora import Node

node = Node()
print("[arm_control] 机械臂节点已启动 (Layer 0: mock)", flush=True)


def grab(item):
    """Layer 0: 模拟抓取。现场替换为机械臂运动控制。"""
    time.sleep(1.5)  # 模拟抓取+放置耗时
    return True


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "arm_cmd":
        continue

    cmd = json.loads(event["value"].to_pylist()[0])
    item = cmd["item"]
    print(f"[arm_control] [mock] 抓取 {item} -> 放入包中...", flush=True)

    ok = grab(item)
    print(f"[arm_control] [mock] {'已将' if ok else '抓取失败'} {item} {'放入包中' if ok else ''}", flush=True)

    arm_done = {"success": ok, "item": item}
    node.send_output("arm_done", pa.array([json.dumps(arm_done, ensure_ascii=False)]))
