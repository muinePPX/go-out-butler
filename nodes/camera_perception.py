"""深度相机感知节点 - Layer 0 打印 mock 日志

现场接入时，替换 perceive() 为真实相机识别：
  深度相机取图 -> 二维码识别 / NPU 目标检测 -> 返回物品是否在位
"""
import json
import time
import pyarrow as pa
from dora import Node

node = Node()
print("[camera_perception] 感知节点已启动 (Layer 0: mock)", flush=True)


def perceive(item, qr_code):
    """Layer 0: 模拟识别（默认找到）。现场替换为深度相机识别。"""
    time.sleep(0.5)  # 模拟识别耗时
    return True


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "camera_cmd":
        continue

    cmd = json.loads(event["value"].to_pylist()[0])
    item = cmd["item"]
    qr = cmd["qr_code"]
    print(f"[camera_perception] [mock] 识别 {item} (二维码:{qr})...", flush=True)

    found = perceive(item, qr)
    print(f"[camera_perception] [mock] {'已识别' if found else '未找到'} {item}", flush=True)

    item_result = {"found": found, "item": item, "qr_code": qr}
    node.send_output("item_result", pa.array([json.dumps(item_result, ensure_ascii=False)]))
