"""讯飞语音听写(流式版)WebAPI 封装

功能: 麦克风录音 -> 上传讯飞 -> 返回识别文字
依赖: sounddevice, numpy, websocket-client (见 requirements.txt)
配置: config/xunfei.json (从 config/xunfei.example.json 复制并填Key)
文档: https://www.xfyun.cn/doc/asr/voicedictation/API.html

调用示例:
    from asr_xunfei import listen
    text = listen()   # 录音并识别,返回文字;失败返回 None
"""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

# 讯飞配置文件路径(相对本文件: ../config/xunfei.json)
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "xunfei.json")

# 讯飞听写服务地址
_IAT_HOST = "iat-api.xfyun.cn"
_IAT_PATH = "/v2/iat"

# 音频参数(讯飞要求: 16kHz / 16bit / 单声道)
_SAMPLE_RATE = 16000
_FRAME_BYTES = 1280   # 40ms 音频 = 640采样 * 2字节 = 1280字节


def load_config():
    """读取讯飞配置。未配置返回 None。"""
    if not os.path.exists(_CONFIG_PATH):
        return None
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def has_key():
    """是否已配置讯飞密钥(决定 voice_input 用语音还是降级文字)。"""
    cfg = load_config()
    return bool(cfg and cfg.get("appid") and cfg.get("api_key") and cfg.get("api_secret"))


# ---------------- 鉴权: HMAC-SHA256 签名生成 wss URL ----------------

def _build_auth_url(api_key, api_secret):
    """按讯飞文档7步生成鉴权 WebSocket URL。"""
    # RFC1123 格式 UTC 时间
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    # Step3: 签名原始字段
    signature_origin = f"host: {_IAT_HOST}\ndate: {date}\nGET {_IAT_PATH} HTTP/1.1"
    # Step4-5: HMAC-SHA256 签名后 Base64
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode()
    # Step6: authorization_origin
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    # Step7: Base64 得到 authorization
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode()
    # 拼接最终 URL
    params = {"authorization": authorization, "date": date, "host": _IAT_HOST}
    return f"wss://{_IAT_HOST}{_IAT_PATH}?{urlencode(params)}"


# ---------------- 录音: 麦克风采集 PCM ----------------

def record_pcm(sample_rate=_SAMPLE_RATE, silence_sec=2.0, max_sec=10.0,
               frame_ms=40, energy_threshold=250):
    """录音: 检测到说话开始,静音 silence_sec 秒自动停止,最长 max_sec。

    返回 PCM bytes(16bit/单声道)。未检测到说话返回 None。
    energy_threshold: 能量阈值,环境嘈杂可调高。打印能量帮助调试。
    """
    import numpy as np
    import sounddevice as sd

    samples_per_frame = int(sample_rate * frame_ms / 1000)  # 40ms = 640 采样
    silence_limit = int(silence_sec * 1000 / frame_ms)       # 静音多少帧算结束
    max_frames = int(max_sec * 1000 / frame_ms)
    min_speech = int(0.3 * 1000 / frame_ms)                  # 至少说0.3秒

    print("[录音] 开始说话(说完停顿2秒自动结束,最长10秒)...", flush=True)
    frames = []
    has_speech = False
    speech_count = 0
    silence_count = 0

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16",
                        blocksize=samples_per_frame) as stream:
        for _ in range(max_frames):
            data, _ = stream.read(samples_per_frame)
            frames.append(data.tobytes())
            energy = int(np.abs(data).mean())

            if energy > energy_threshold:
                has_speech = True
                speech_count += 1
                silence_count = 0
            elif has_speech:
                silence_count += 1
                if silence_count >= silence_limit and speech_count >= min_speech:
                    break

    if not has_speech:
        print("[录音] 未检测到说话内容", flush=True)
        return None

    pcm = b"".join(frames)
    duration = len(pcm) / 2 / sample_rate
    print(f"[录音] 完成,时长 {duration:.1f}秒", flush=True)
    return pcm


# ---------------- 识别: WebSocket 上传并接收结果 ----------------

def recognize(pcm_bytes, language="zh_cn", accent="mandarin"):
    """把 PCM bytes 上传讯飞,返回识别文字。失败抛 RuntimeError。"""
    import threading
    import websocket  # websocket-client

    cfg = load_config()
    if not cfg:
        raise RuntimeError("未找到 config/xunfei.json,请按 docs/讯飞ASR接入说明.md 配置密钥")

    url = _build_auth_url(cfg["api_key"], cfg["api_secret"])
    app_id = cfg["appid"]

    # 讯飞是流式识别: 服务端边收边返回结果。
    # 必须边发边收(并行),否则返回数据堆积会导致连接断开(WinError 10053)。
    # 方案: 子线程发送音频帧, 主线程接收结果。
    ws = websocket.create_connection(url, timeout=15)
    result_parts = []
    send_error = [None]

    def send_audio():
        """子线程: 分帧发送音频"""
        chunks = [pcm_bytes[i:i + _FRAME_BYTES]
                  for i in range(0, len(pcm_bytes), _FRAME_BYTES)]
        if not chunks:
            try:
                ws.send(json.dumps({"data": {"status": 2}}))
            except Exception as e:
                send_error[0] = e
            return
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            audio_b64 = base64.b64encode(chunk).decode()
            if i == 0:
                payload = {
                    "common": {"app_id": app_id},
                    "business": {
                        "language": language,
                        "domain": "iat",
                        "accent": accent,
                        "ptt": 1,            # 开启标点
                    },
                    "data": {
                        "status": 0,
                        "format": f"audio/L16;rate={_SAMPLE_RATE}",
                        "encoding": "raw",
                        "audio": audio_b64,
                    },
                }
            else:
                payload = {
                    "data": {
                        "status": 2 if is_last else 1,
                        "format": f"audio/L16;rate={_SAMPLE_RATE}",
                        "encoding": "raw",
                        "audio": audio_b64,
                    }
                }
            try:
                ws.send(json.dumps(payload))
            except Exception as e:
                send_error[0] = e
                return
            time.sleep(0.04)   # 讯飞要求 40ms 间隔

    # 启动发送子线程
    sender = threading.Thread(target=send_audio, daemon=True)
    sender.start()

    # 主线程接收结果,直到收到 status==2 (最后一块)
    try:
        while True:
            try:
                message = ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            if not message:
                break
            data = json.loads(message)
            code = data.get("code", 0)
            if code != 0:
                raise RuntimeError(f"讯飞错误码 {code}: {data.get('message', '未知错误')}")
            result = data.get("data", {}).get("result", {})
            for w in result.get("ws", []):
                for cw in w.get("cw", []):
                    result_parts.append(cw.get("w", ""))
            if data.get("data", {}).get("status") == 2:
                break
    finally:
        sender.join(timeout=2)
        ws.close()

    if send_error[0]:
        raise RuntimeError(f"发送失败: {send_error[0]}")
    return "".join(result_parts)


# ---------------- 一条龙: 录音 + 识别 ----------------

def listen(language="zh_cn", accent="mandarin"):
    """录音并识别,返回文字。任何环节失败返回 None(节点会降级为文字输入)。"""
    if not has_key():
        return None
    pcm = record_pcm()
    if pcm is None:
        return None
    text = recognize(pcm, language=language, accent=accent)
    text = text.strip()
    print(f"[ASR] 识别结果: {text}", flush=True)
    return text if text else None


if __name__ == "__main__":
    # 直接运行本文件也可测试
    print("=== 讯飞语音听写 单独测试 ===")
    if not has_key():
        print("未配置密钥。请复制 config/xunfei.example.json 为 config/xunfei.json 并填入密钥。")
    else:
        result = listen()
        print(f"\n最终识别: {result}")
