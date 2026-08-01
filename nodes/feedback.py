"""反馈节点 - Layer 0 用 print 文字替代 TTS

现场接入时，替换 speak() 为真实 TTS：
  final_status -> 组织话术 -> TTS 语音播报
"""
import json
import pyarrow as pa
from dora import Node

node = Node()
print("[feedback] 反馈节点已启动 (Layer 0: print)", flush=True)


def build_message(status):
    """根据最终状态组织反馈话术"""
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

    # Layer 0: 文字输出
    # 现场替换为：TTS 语音合成 + 播放
    print(f"[feedback] {msg}", flush=True)
    node.send_output("response", pa.array([msg]))
