"""深度相机感知节点 - Layer 0 打印 mock 日志

现场接入时，替换 perceive() 各阶段为真实相机识别：
  深度相机取图 -> 二维码识别 / NPU 目标检测 -> 返回物品是否在位
注意: 真实实现需保持 perceive() 返回格式不变:
  {"found": bool, "item": str, "qr_code": str | None,
   "confidence": float | None, "error": str | None}
"""
import json
import os
import time
import traceback

import pyarrow as pa
from dora import Node

node = Node()

# ---- Layer 0 mock 参数 ----
MOCK_PHASE_DELAY = 0.17  # 每个识别阶段的模拟耗时(秒), 3 阶段共约 0.5s
MOCK_CONFIDENCE = 0.98   # 模拟识别置信度
# 环境变量 CAMERA_MOCK_MISS=物品名 时该物品强制识别不到, 用于演示/测试未找到路径
MOCK_MISS = os.environ.get("CAMERA_MOCK_MISS", "")

print("[camera_perception] 感知节点已启动 (Layer 0: mock)", flush=True)


def perceive(item, qr_code):
    """Layer 0: 模拟识别全流程（默认找到）。

    现场按阶段替换为真实识别(各阶段注释已标出), 保持返回格式不变:
      找到:   {"found": True,  ..., "confidence": 0.0~1.0, "error": None}
      未找到: {"found": False, ..., "confidence": None,    "error": "原因"}
    """
    result = {"found": False, "item": item, "qr_code": qr_code,
              "confidence": None, "error": None}

    if not item:
        result["error"] = "物品名为空"
        return result

    # ---- 阶段 1: 打开深度相机, 取一帧彩色+深度图 ----
    # 现场替换为: 相机 SDK 取流 / 订阅 ROS image+depth topic 各一帧
    print("[camera_perception] [mock]   1. 相机取图(彩色+深度)", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # ---- 阶段 2: 在视野中检测目标 ----
    if qr_code:
        # 现场替换为: 二维码检测(pyzbar / OpenCV QRCodeDetector)扫描彩色图
        print(f"[camera_perception] [mock]   2. 扫描视野内二维码 (目标:{qr_code})", flush=True)
    else:
        # 现场替换为: NPU 目标检测模型按物品名识别(无二维码时的兜底路径)
        print(f"[camera_perception] [mock]   2. NPU 目标检测识别 {item} (无二维码)", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # Layer 0 模拟"视野中未找到"(物品被拿走/遮挡), 真实场景由检测置信度阈值判断
    if MOCK_MISS and MOCK_MISS == item:
        result["error"] = "视野中未检测到目标(mock 强制未找到)"
        print(f"[camera_perception] [mock]   ! {result['error']}", flush=True)
        return result

    # ---- 阶段 3: 比对确认 + 深度定位 ----
    # 现场替换为: 二维码内容与目标比对/检测框置信度判断, 深度图估计物品三维位置
    print(f"[camera_perception] [mock]   3. 目标确认, 深度定位 {item}", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    result["found"] = True
    result["confidence"] = MOCK_CONFIDENCE
    return result


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "camera_cmd":
        continue

    # ---- 解析识别命令; 异常时回复未找到, 避免调度器在 PERCEIVE 状态死等 ----
    try:
        if event["value"] is None:
            raise ValueError("empty value")
        cmd = json.loads(event["value"].to_pylist()[0])
        item = cmd["item"]
        qr = cmd.get("qr_code")  # 允许为空, 走 NPU 检测路径
        index = cmd.get("index", -1)
    except Exception as e:
        print(f"[camera_perception] 无效 camera_cmd 已忽略: {e}", flush=True)
        node.send_output("item_result", pa.array([json.dumps(
            {"found": False, "item": None, "qr_code": None, "index": -1,
             "error": f"invalid camera_cmd: {e}"}, ensure_ascii=False)]))
        continue

    print(f"[camera_perception] [mock] 收到识别指令: {item} (二维码:{qr}, 序号 {index})", flush=True)

    # ---- 执行识别; 异常兜底(mock 不应抛出, 现场相机可能掉线/取流超时) ----
    t0 = time.monotonic()
    try:
        result = perceive(item, qr)
    except Exception as e:
        traceback.print_exc()
        result = {"found": False, "item": item, "qr_code": qr,
                  "confidence": None, "error": f"{type(e).__name__}: {e}"}
    elapsed = time.monotonic() - t0

    if result["found"]:
        print(f"[camera_perception] [mock] 已识别 {item} "
              f"(置信度 {result['confidence']}, 耗时 {elapsed:.1f}s)", flush=True)
    else:
        print(f"[camera_perception] [mock] 未找到 {item} ({result['error']})", flush=True)

    # ---- 上报结果, 回显 index 便于调度器核对 ----
    item_result = {
        "found": result["found"],
        "item": item,
        "qr_code": qr,
        "index": index,
        "confidence": result["confidence"],
        "elapsed": round(elapsed, 2),
        "error": result["error"],
    }
    node.send_output("item_result", pa.array([json.dumps(item_result, ensure_ascii=False)]))
