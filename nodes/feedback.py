"""反馈节点 - TTS语音播报 + print文字降级

有edge-tts依赖 -> 语音播报反馈话术
无依赖或播报失败 -> print文字保底(演示不中断)

输入: final_status (JSON: {"success":[...], "failed":[...], "total":N})
输出: response (纯字符串, 反馈话术)
"""
import json
import os
import sys

# 让节点能找到 lib/ 目录下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pyarrow as pa
from dora import Node
from tts_edge import has_tts, speak

node = Node()

USE_TTS = has_tts()
if USE_TTS:
    print("[feedback] 已启用TTS语音播报", flush=True)
else:
    print("[feedback] 未启用TTS,使用文字输出 (pip install edge-tts miniaudio 可启用)", flush=True)


def build_message(status):
    """根据最终状态组织反馈话术。"""
    success = status.get("success", [])
    failed = status.get("failed", [])

    if not success and not failed:
        return status.get("error", "未能处理您的请求")
    if failed:
        ok_part = "、".join(success) if success else "无"
        fail_part = "、".join(failed)
        return f"已为您准备: {ok_part}；但未能找到: {fail_part}，请自行检查。"
    return f"已为您准备好: {'、'.join(success)}。祝您出行顺利！"


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "final_status":
        continue

    status = json.loads(event["value"].to_pylist()[0])
    msg = build_message(status)

    # 始终打印文字(保底 + 调试可见)
    print(f"[feedback] {msg}", flush=True)

    # 有TTS则语音播报,失败不影响演示
    if USE_TTS:
        ok = speak(msg)
        if not ok:
            print("[feedback] TTS播报失败,请看上方文字", flush=True)

    # 保持与原版一致: 发送纯字符串
    node.send_output("response", pa.array([msg]))
