"""机械臂控制节点 - Layer 0 打印 mock 日志

现场接入时，替换 grab() 各阶段为真实机械臂控制：
  ROS 关节轨迹话题 / MoveIt / 机械臂 SDK -> 抓取物品 -> 放入门口包中
注意: 真实实现需保持 grab() 返回格式不变:
  {"success": bool, "item": str, "error": str | None}
"""
import json
import os
import time
import traceback

import pyarrow as pa
from dora import Node

node = Node()

# ---- Layer 0 mock 参数 ----
MOCK_PHASE_DELAY = 0.25  # 每个动作阶段的模拟耗时(秒), 6 阶段共 1.5s
# 环境变量 ARM_MOCK_FAIL=物品名 时该物品强制抓取失败, 用于演示/测试失败路径
MOCK_FORCE_FAIL = os.environ.get("ARM_MOCK_FAIL", "")

print("[arm_control] 机械臂节点已启动 (Layer 0: mock)", flush=True)


def grab(item):
    """Layer 0: 模拟 取物->放置 全流程。

    现场按阶段替换为真实控制(各阶段注释已标出), 保持返回格式不变:
      成功: {"success": True,  "item": item, "error": None}
      失败: {"success": False, "item": item, "error": "失败原因"}
    """
    result = {"success": False, "item": item, "error": None}

    if not item:
        result["error"] = "物品名为空"
        return result

    # ---- 阶段 1: 移动到物品上方预抓取位 ----
    # 现场替换为: 发布关节轨迹 / MoveIt plan&execute 到预抓取位姿
    print(f"[arm_control] [mock]   1. 移动到 {item} 上方预抓取位", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # ---- 阶段 2: 下降接近物品, 闭合夹爪 ----
    # 现场替换为: 笛卡尔下降 + 夹爪闭合(话题/服务), 读夹爪行程或电流确认夹持
    print(f"[arm_control] [mock]   2. 下降并闭合夹爪, 抓取 {item}", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # Layer 0 模拟"夹爪空夹"失败(物品不在/识别偏差), 真实场景由夹爪反馈判断
    if MOCK_FORCE_FAIL and MOCK_FORCE_FAIL == item:
        result["error"] = "夹爪空夹, 未抓到物品(mock 强制失败)"
        print(f"[arm_control] [mock]   ! {result['error']}", flush=True)
        return result

    # ---- 阶段 3: 垂直抬起物品 ----
    # 现场替换为: 沿 Z 轴抬起到安全高度
    print(f"[arm_control] [mock]   3. 抬起 {item}", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # ---- 阶段 4: 移动到放置位(包)上方 ----
    # 现场替换为: 移动到包上方固定示教点(包固定于机身/门口)
    print(f"[arm_control] [mock]   4. 携带 {item} 移动到包上方", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # ---- 阶段 5: 松开夹爪, 放入包中 ----
    # 现场替换为: 夹爪张开, 可选: 短暂等待物品落稳
    print(f"[arm_control] [mock]   5. 松开夹爪, {item} 放入包中", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    # ---- 阶段 6: 回到初始收拢位 ----
    # 现场替换为: 回到安全收拢位姿, 避免遮挡相机/干涉底盘移动
    print("[arm_control] [mock]   6. 机械臂回到初始位", flush=True)
    time.sleep(MOCK_PHASE_DELAY)

    result["success"] = True
    return result


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "arm_cmd":
        continue

    # ---- 解析抓取命令; 异常时回复失败应答, 避免调度器在 GRAB 状态死等 ----
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

    print(f"[arm_control] [mock] 收到抓取指令: {item} (序号 {index})", flush=True)

    # ---- 执行抓取; 异常兜底(mock 不应抛出, 现场真实控制可能通信失败/超限) ----
    t0 = time.monotonic()
    try:
        result = grab(item)
    except Exception as e:
        traceback.print_exc()
        result = {"success": False, "item": item,
                  "error": f"{type(e).__name__}: {e}"}
    elapsed = time.monotonic() - t0

    if result["success"]:
        print(f"[arm_control] [mock] 已将 {item} 放入包中 (耗时 {elapsed:.1f}s)", flush=True)
    else:
        print(f"[arm_control] [mock] 抓取失败: {item} ({result['error']})", flush=True)

    # ---- 上报结果, 回显 index 便于调度器核对 ----
    arm_done = {
        "success": result["success"],
        "item": item,
        "index": index,
        "elapsed": round(elapsed, 2),
        "error": result["error"],
    }
    node.send_output("arm_done", pa.array([json.dumps(arm_done, ensure_ascii=False)]))
