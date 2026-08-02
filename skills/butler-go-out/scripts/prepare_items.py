#!/usr/bin/env python3
"""出门管家 - 场景物品清单规划

根据用户出行场景，输出要带的物品清单和对应点位（供 M-Claw 协调机器人取物）。

用法:
    python prepare_items.py <场景>   # 生成物品清单JSON
    python prepare_items.py list     # 列出支持的场景
    python prepare_items.py          # 显示用法

场景: 运动、开会、上课
"""
import json
import os
import sys

# 场景配置文件(相对本文件: ../config/scenarios.json)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "scenarios.json")


def load_scenarios():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def plan(scene):
    """根据场景生成物品清单。精确匹配优先，其次模糊匹配。"""
    scenarios = load_scenarios()
    # 精确匹配
    if scene in scenarios:
        items = scenarios[scene]["items"]
        return {"scene": scene, "items": items, "total": len(items)}
    # 模糊匹配:输入包含场景关键词即可(如"我要去运动"匹配"运动")
    for key in scenarios:
        if key in scene:
            items = scenarios[key]["items"]
            return {"scene": key, "items": items, "total": len(items)}
    return {
        "scene": scene,
        "items": [],
        "total": 0,
        "error": f"未识别的场景: {scene}",
        "supported": list(scenarios.keys()),
    }


def main():
    if len(sys.argv) < 2:
        print("出门管家 - 场景物品清单规划")
        print("用法:")
        print("  python prepare_items.py <场景>   生成物品清单JSON")
        print("  python prepare_items.py list     列出支持的场景")
        print("场景: 运动、开会、上课")
        sys.exit(0)

    arg = sys.argv[1]

    if arg == "list":
        scenarios = load_scenarios()
        print("支持的场景:")
        for scene, data in scenarios.items():
            names = "、".join(i["name"] for i in data["items"])
            print(f"  {scene}: {names}")
        return

    result = plan(arg)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
