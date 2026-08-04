"""M-Claw 决策节点 - Layer 0 用 scenarios.json 规则查表替代 M-Claw API

现场接入真实 M-Claw 时，替换 decide() 各阶段为：
  user_text -> M-Claw 意图理解 + 任务拆解 -> 返回物品清单
注意: 真实实现需保持 decide() 返回格式不变:
  {"scene": str | None, "items": [...], "matched_by": str | None, "error": str | None}
"""
import os
import json
import time
import traceback

import pyarrow as pa
from dora import Node

# config 目录：相对于 nodes/ 上一级的 config/
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")

# Layer 0 场景别名表: 模拟 M-Claw 的同义意图理解能力(现场由 API 处理, 删除此表)
ALIASES = {
    "运动": ["跑步", "健身", "锻炼", "打球", "游泳", "晨跑", "夜跑", "爬山"],
    "开会": ["上班", "工作", "会议", "出差", "见客户", "面试"],
    "上课": ["上学", "学习", "课程", "自习", "考试"],
}


def load_scenarios():
    path = os.path.join(CONFIG_DIR, "scenarios.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


try:
    SCENARIOS = load_scenarios()
    print(f"[mclaw_decision] 已加载场景配置: {list(SCENARIOS.keys())}", flush=True)
except Exception as e:
    # 配置缺失时节点保持存活: 所有输入走"未识别"错误应答, 而不是启动即崩
    SCENARIOS = {}
    print(f"[mclaw_decision] 场景配置加载失败({e}), 所有输入将无法识别", flush=True)

node = Node()
print("[mclaw_decision] 决策节点已启动 (Layer 0: 规则查表)", flush=True)


def _valid_items(scene):
    """取出场景物品清单并校验必要字段。

    调度器会直接访问 item["name"]/["waypoint"]/["qr_code"],
    缺字段的物品必须在决策层过滤掉, 否则调度器 KeyError 崩溃。
    """
    entry = SCENARIOS.get(scene) or {}
    items = entry.get("items") or []
    valid = []
    for it in items:
        if isinstance(it, dict) and all(it.get(k) for k in ("name", "waypoint", "qr_code")):
            valid.append(it)
        else:
            print(f"[mclaw_decision] 场景[{scene}]物品配置缺字段已跳过: {it}", flush=True)
    return valid


def decide(user_text):
    """Layer 0: 规则查表模拟意图理解+任务拆解。

    现场按阶段替换为 M-Claw API(各阶段注释已标出), 保持返回格式不变:
      成功: {"scene": "运动", "items": [...], "matched_by": "exact|keyword|alias", "error": None}
      失败: {"scene": None, "items": [], "matched_by": None, "error": "原因"}
    """
    result = {"scene": None, "items": [], "matched_by": None, "error": None}

    text = (user_text or "").strip()
    if not text:
        result["error"] = "输入为空"
        return result

    # ---- 阶段 1: 意图理解(场景识别) ----
    # 现场替换为: M-Claw API 意图理解(删除下方规则与别名表)
    scene, matched_by = None, None
    if text in SCENARIOS:
        scene, matched_by = text, "exact"          # 精确匹配: "运动"
    else:
        for key in SCENARIOS:                       # 关键词匹配: "我要去运动"
            if key in text:
                scene, matched_by = key, "keyword"
                break
        if scene is None:                           # 别名匹配: "我要去跑步" -> 运动
            for key, words in ALIASES.items():
                if key in SCENARIOS and any(w in text for w in words):
                    scene, matched_by = key, "alias"
                    break

    if scene is None:
        result["error"] = f"未识别的场景: {text}"
        print(f"[mclaw_decision] [mock]   ! {result['error']}", flush=True)
        return result
    print(f"[mclaw_decision] [mock]   1. 意图理解: \"{text}\" -> 场景[{scene}] ({matched_by})", flush=True)

    # ---- 阶段 2: 任务拆解(生成并校验物品清单) ----
    # 现场替换为: M-Claw API 任务拆解(返回场景所需物品清单)
    items = _valid_items(scene)
    if not items:
        result["error"] = f"场景[{scene}]无有效物品配置"
        print(f"[mclaw_decision] [mock]   ! {result['error']}", flush=True)
        return result
    names = [i["name"] for i in items]
    print(f"[mclaw_decision] [mock]   2. 任务拆解: {scene} -> 物品清单 {names}", flush=True)

    result.update(scene=scene, items=items, matched_by=matched_by)
    return result


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "user_text":
        continue

    # ---- 解析用户输入; 异常时回复错误计划, 避免调度器/反馈链路无响应 ----
    try:
        if event["value"] is None:
            raise ValueError("empty value")
        user_text = str(event["value"].to_pylist()[0]).strip()
    except Exception as e:
        print(f"[mclaw_decision] 无效 user_text 已忽略: {e}", flush=True)
        node.send_output("task_plan", pa.array([json.dumps(
            {"scene": None, "items": [], "error": f"invalid user_text: {e}"},
            ensure_ascii=False)]))
        continue

    print(f"[mclaw_decision] 收到用户输入: {user_text}", flush=True)

    # ---- 执行决策; 异常兜底(现场 API 可能超时/限流/返回异常) ----
    t0 = time.monotonic()
    try:
        result = decide(user_text)
    except Exception as e:
        traceback.print_exc()
        result = {"scene": None, "items": [], "matched_by": None,
                  "error": f"{type(e).__name__}: {e}"}
    elapsed = time.monotonic() - t0

    # ---- 输出任务计划(保持 task_scheduler 期望的契约: error 字段触发错误分支) ----
    if result["error"] is None:
        task_plan = {"scene": result["scene"], "items": result["items"],
                     "matched_by": result["matched_by"]}
    else:
        print(f"[mclaw_decision] 决策失败: {result['error']} (耗时 {elapsed:.2f}s)", flush=True)
        task_plan = {"scene": user_text, "items": [], "error": result["error"]}

    node.send_output("task_plan", pa.array([json.dumps(task_plan, ensure_ascii=False)]))
