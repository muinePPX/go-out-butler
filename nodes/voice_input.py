"""语音输入节点

有讯飞密钥 -> 麦克风录音 + 讯飞识别
无密钥或识别失败 -> 降级为终端文字输入(stdin)

输出: user_text (纯字符串, 如 "我要去运动")
触发: dataflow.yml 中每 500ms 的 tick 信号(仅首次触发录音,之后跳过)
"""
import json
import os
import sys

# 让节点能找到 lib/ 目录下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pyarrow as pa
from dora import Node

from asr_xunfei import has_key, listen

node = Node()

# 是否启用语音模式
USE_VOICE = has_key()
if USE_VOICE:
    print("[voice_input] 已检测到讯飞配置,启用语音输入模式", flush=True)
    print("[voice_input] 启动后请直接说话,说完停顿2秒自动识别", flush=True)
else:
    print("[voice_input] 未检测到讯飞配置,使用文字输入模式", flush=True)
    print("[voice_input] (配置语音见 docs/讯飞ASR接入说明.md)", flush=True)

# 标志位: 防止 tick 重复触发录音。首次录音成功后不再触发。
_listened = False


def get_text():
    """获取用户输入。语音模式优先,失败降级文字。"""
    global _listened
    if USE_VOICE:
        try:
            text = listen()
            if text:
                return text
            print("[voice_input] 语音未识别到内容,降级为文字输入", flush=True)
        except Exception as e:
            print(f"[voice_input] 语音识别异常: {e}，降级为文字输入", flush=True)
    # 降级: 终端手动输入
    return input("请输入出行场景(如:我要去运动)> ").strip()


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "tick":
        continue
    if _listened:
        # 已完成一次输入,后续 tick 跳过(避免重复录音)
        # 如需再次输入,重启 dataflow 即可
        continue

    _listened = True   # 标记,防止重入
    text = get_text()
    if text:
        print(f"[voice_input] 输入完成: {text}", flush=True)
        # 保持与原版一致: 发送纯字符串,兼容 mclaw_decision
        node.send_output("user_text", pa.array([text]))
        # _listened 保持 True,不再触发。机器人将开始执行任务。
