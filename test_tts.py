"""edge-tts 独立测试脚本(不依赖 Dora,在家先测通)

用法:
    1. pip install edge-tts miniaudio
    2. python test_tts.py

会播放一句话,听到声音就成功。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

from tts_edge import has_tts, speak


def main():
    print("=" * 50)
    print("  edge-tts 语音合成 - 独立测试")
    print("=" * 50)

    if not has_tts():
        print("\n[未安装] 缺少 edge-tts 或 miniaudio")
        print("请运行: pip install edge-tts miniaudio")
        sys.exit(1)

    text = "已为您准备好水杯和毛巾。祝您出行顺利！"
    print(f"\n即将播报: {text}")
    print("(需要联网生成语音,首次稍慢)\n")

    ok = speak(text)
    if ok:
        print("\n[成功] 播放完成! feedback 节点可以使用语音播报了。")
    else:
        print("\n[失败] 播报出错,常见原因:")
        print("  1. 网络不通 -> edge-tts 需要联网(调微软服务)")
        print("  2. 音频设备问题 -> 检查扬声器/音量")
        print("  3. miniaudio 解码问题 -> 重新安装: pip install --upgrade miniaudio")
        sys.exit(1)


if __name__ == "__main__":
    main()
