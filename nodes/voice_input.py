"""语音输入节点 - Layer 0 用 stdin 文字输入替代 ASR

现场接入真实 ASR 时，替换 read_stdin_nonblocking() 为：
  采集麦克风音频 -> ASR 识别 -> 返回文字
"""
import sys
import pyarrow as pa
from dora import Node

node = Node()
print("[voice_input] 节点已启动，请在终端输入出行场景（如：运动 / 开会 / 上课）", flush=True)


def read_stdin_nonblocking():
    """非阻塞读取 stdin，无数据返回 None。

    开发板(Linux)上用 select 实现非阻塞；
    Windows 本地不支持 select stdin，返回 None（不会卡住）。
    """
    try:
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline().strip()
            return line if line else None
    except (OSError, ValueError):
        pass
    return None


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "tick":
        continue

    # Layer 0: 非阻塞读取终端输入
    # 现场替换为：采集音频 -> ASR 语音识别
    text = read_stdin_nonblocking()
    if text:
        print(f"[voice_input] 识别到输入: {text}", flush=True)
        node.send_output("user_text", pa.array([text]))
