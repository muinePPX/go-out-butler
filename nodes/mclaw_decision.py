"""M-Claw 决策节点 - Layer 0 用 scenarios.json 规则查表替代 M-Claw API

现场接入真实 M-Claw 时，替换 decide() 为：
  user_text -> M-Claw 意图理解 + 任务拆解 -> 返回物品清单
"""
import os
import json
import pyarrow as pa
from dora import Node

# config 目录：相对于 nodes/ 上一级的 config/
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def load_scenarios():
    path = os.path.join(CONFIG_DIR, "scenarios.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


SCENARIOS = load_scenarios()
print(f"[mclaw_decision] 已加载场景配置: {list(SCENARIOS.keys())}", flush=True)

node = Node()


def decide(user_text):
    """Layer 0: 规则查表。现场替换为 M-Claw API 调用。"""
    # 精确匹配
    if user_text in SCENARIOS:
        return SCENARIOS[user_text]["items"], user_text
    # 模糊匹配：输入包含场景关键词即可
    for key in SCENARIOS:
        if key in user_text:
            return SCENARIOS[key]["items"], key
    return None, user_text


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "user_text":
        continue

    user_text = event["value"].to_pylist()[0]
    print(f"[mclaw_decision] 收到用户输入: {user_text}", flush=True)

    items, scene = decide(user_text)

    if items is None:
        print(f"[mclaw_decision] 未识别场景: {user_text}", flush=True)
        task_plan = {"scene": user_text, "items": [], "error": f"未识别的场景: {user_text}"}
    else:
        task_plan = {"scene": scene, "items": items}
        item_names = [i["name"] for i in items]
        print(f"[mclaw_decision] 场景={scene}, 物品清单={item_names}", flush=True)

    node.send_output("task_plan", pa.array([json.dumps(task_plan, ensure_ascii=False)]))
