"""任务调度节点（状态机）

接收 task_plan，依次对每个物品执行：导航 -> 识别 -> 对齐(视觉伺服) -> 抓取
状态流转: IDLE -> NAV -> PERCEIVE -> ALIGN -> GRAB -> (下一物品) -> DONE
"""
import json
import pyarrow as pa
from dora import Node

node = Node()

# 状态机状态
IDLE, NAV, PERCEIVE, ALIGN, GRAB, DONE = "IDLE", "NAV", "PERCEIVE", "ALIGN", "GRAB", "DONE"
state = IDLE
items = []          # 待处理物品列表
idx = 0             # 当前物品索引
results = {"success": [], "failed": []}  # 最终结果

print("[task_scheduler] 调度节点已启动", flush=True)


def start_next_item():
    """开始处理下一个物品：下发导航命令"""
    global state
    if idx >= len(items):
        finish()
        return
    item = items[idx]
    nav_cmd = {"waypoint": item["waypoint"], "item": item["name"], "index": idx}
    print(f"[task_scheduler] [{state}->NAV] 导航到 {item['waypoint']} 取 {item['name']}", flush=True)
    node.send_output("nav_cmd", pa.array([json.dumps(nav_cmd, ensure_ascii=False)]))
    state = NAV


def finish():
    """全部物品处理完毕，发送最终状态"""
    global state
    state = DONE
    final_status = {
        "success": results["success"],
        "failed": results["failed"],
        "total": len(items),
    }
    print(f"[task_scheduler] [DONE] 完成! 成功={results['success']}, 失败={results['failed']}", flush=True)
    node.send_output("final_status", pa.array([json.dumps(final_status, ensure_ascii=False)]))


for event in node:
    if event["type"] != "INPUT":
        continue

    eid = event["id"]
    data = event["value"].to_pylist()[0] if event["value"] is not None else None

    # 收到任务计划 -> 初始化并开始第一个物品
    if eid == "task_plan":
        plan = json.loads(data)
        if plan.get("error"):
            print(f"[task_scheduler] 决策错误: {plan['error']}", flush=True)
            node.send_output("final_status", pa.array([json.dumps(
                {"success": [], "failed": [], "total": 0, "error": plan["error"]},
                ensure_ascii=False)]))
            state = DONE
            continue
        items = plan["items"]
        idx = 0
        results = {"success": [], "failed": []}
        print(f"[task_scheduler] [IDLE] 收到任务计划, 共 {len(items)} 个物品", flush=True)
        start_next_item()

    # 导航完成 -> 开始识别
    elif eid == "nav_done" and state == NAV:
        result = json.loads(data)
        item = items[idx]
        if not result.get("success", False):
            print(f"[task_scheduler] [NAV->FAIL] 导航失败: {item['name']}", flush=True)
            results["failed"].append(item["name"])
            idx += 1
            start_next_item()
        else:
            print(f"[task_scheduler] [NAV->PERCEIVE] 到达, 开始识别 {item['name']}", flush=True)
            camera_cmd = {"item": item["name"], "qr_code": item.get("qr_code"), "index": idx}
            # 若物品配置了颜色目标(HSV 模式)，则透传 target_colors
            if item.get("target_colors"):
                camera_cmd["mode"] = "color"
                camera_cmd["target_colors"] = item["target_colors"]
                camera_cmd.pop("qr_code", None)
            node.send_output("camera_cmd", pa.array([json.dumps(camera_cmd, ensure_ascii=False)]))
            state = PERCEIVE

    # 识别结果 -> 找到则先视觉伺服对齐，没找到则跳过
    elif eid == "item_result" and state == PERCEIVE:
        result = json.loads(data)
        item = items[idx]
        if not result.get("found", False):
            print(f"[task_scheduler] [PERCEIVE->SKIP] 未找到 {item['name']}", flush=True)
            results["failed"].append(item["name"])
            idx += 1
            start_next_item()
        else:
            print(f"[task_scheduler] [PERCEIVE->ALIGN] 找到 {item['name']}, 开始对齐", flush=True)
            # 对齐目标颜色: 物品配置优先, 否则用识别结果里命中的颜色
            target_colors = item.get("target_colors")
            if not target_colors and result.get("color"):
                target_colors = [result["color"]]
            # 对准收敛距离: 摄像头与目标最后停到 65cm; 物品配置优先, 否则默认 0.65m
            servo_cmd = {
                "item": item["name"],
                "index": idx,
                "target_colors": target_colors or [],
                "servo_params": {"grasp_depth_m": item.get("grasp_depth_m", 0.65)},
                "timeout": item.get("servo_timeout", 40),
            }
            node.send_output("servo_cmd", pa.array([json.dumps(servo_cmd, ensure_ascii=False)]))
            state = ALIGN

    # 对齐结果 -> 对齐成功则抓取，失败则跳过
    elif eid == "servo_result" and state == ALIGN:
        result = json.loads(data)
        item = items[idx]
        if not result.get("aligned", False):
            print(f"[task_scheduler] [ALIGN->SKIP] 对齐失败: {item['name']} ({result.get('error', '')})", flush=True)
            results["failed"].append(item["name"])
            idx += 1
            start_next_item()
        else:
            print(f"[task_scheduler] [ALIGN->GRAB] 对齐完成 {item['name']}, 开始抓取", flush=True)
            arm_cmd = {"item": item["name"], "index": idx}
            node.send_output("arm_cmd", pa.array([json.dumps(arm_cmd, ensure_ascii=False)]))
            state = GRAB

    # 抓取完成 -> 处理下一个
    elif eid == "arm_done" and state == GRAB:
        result = json.loads(data)
        item = items[idx]
        if result.get("success", False):
            print(f"[task_scheduler] [GRAB->OK] 抓取成功: {item['name']}", flush=True)
            results["success"].append(item["name"])
        else:
            print(f"[task_scheduler] [GRAB->FAIL] 抓取失败: {item['name']}", flush=True)
            results["failed"].append(item["name"])
        idx += 1
        start_next_item()
