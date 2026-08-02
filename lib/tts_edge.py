"""edge-tts 语音合成封装

功能: 文字 -> 微软edge-tts生成语音 -> 播放
依赖: edge-tts, miniaudio, sounddevice, numpy (见 requirements.txt)
特点: 无需API Key,免费,中文自然;但需要联网(edge-tts调微软服务)
降级: 未安装或联网失败时,has_tts()返回False,节点自动用print文字

调用示例:
    from tts_edge import has_tts, speak
    if has_tts():
        speak("已为您准备好水杯和毛巾")
"""
import asyncio
import os
import tempfile


def has_tts():
    """是否可用TTS(edge-tts和miniaudio都已安装)。"""
    try:
        import edge_tts  # noqa
        import miniaudio  # noqa
        return True
    except ImportError:
        return False


async def _save_audio(text, voice, path):
    """异步: 调edge-tts生成mp3保存到path。"""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


def speak(text, voice="zh-CN-XiaoxiaoNeural"):
    """文字 -> 语音播放。成功返回True,失败返回False。

    voice: 发音人。常用:
      zh-CN-XiaoxiaoNeural  女声(晓晓,温柔,默认)
      zh-CN-YunxiNeural     男声(云希,沉稳)
      zh-CN-XiaoyiNeural    女声(晓伊,活泼)
    """
    import miniaudio
    import numpy as np
    import sounddevice as sd

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    try:
        # 1. edge-tts 生成 mp3(需联网)
        asyncio.run(_save_audio(text, voice, tmp))
        # 2. miniaudio 解码 mp3 -> PCM(16bit/单声道/16kHz)
        decoded = miniaudio.decode_file(
            tmp,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=16000,
        )
        # 3. sounddevice 播放
        samples = np.frombuffer(decoded.samples, dtype=np.int16)
        sd.play(samples, decoded.sample_rate)
        sd.wait()  # 等播放完
        return True
    except Exception:
        return False
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    print("=== edge-tts 单独测试 ===")
    if not has_tts():
        print("未安装依赖。请运行: pip install edge-tts miniaudio")
    else:
        ok = speak("你好,我是出门管家机器人。")
        print("播放成功" if ok else "播放失败")
