"""讯飞 ASR 独立测试脚本(不依赖 Dora,在家先测通)

用法:
    1. 按 docs/讯飞ASR接入说明.md 配置 config/xunfei.json
    2. pip install -r requirements.txt
    3. python test_asr.py

对着麦克风说一句话(如"我要去运动"),看是否正确识别。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

from asr_xunfei import has_key, listen, load_config


def main():
    print("=" * 50)
    print("  讯飞语音听写 - 独立测试")
    print("=" * 50)

    if not has_key():
        print("\n[未配置] 没有找到 config/xunfei.json")
        print("请复制 config/xunfei.example.json 为 config/xunfei.json,")
        print("并填入你的讯飞 APPID / APIKey / APISecret。")
        print("获取步骤见 docs/讯飞ASR接入说明.md")
        sys.exit(1)

    cfg = load_config()
    print(f"\n[配置] APPID: {cfg['appid'][:4]}****")
    print(f"[配置] 语种: {cfg.get('language', 'zh_cn')} / {cfg.get('accent', 'mandarin')}")
    print('\n现在对着麦克风说一句话,例如:"我要去运动"')
    print("(说完停顿2秒自动结束识别)\n")

    try:
        text = listen()
    except Exception as e:
        print(f"\n[失败] 识别出错: {e}")
        print("常见原因:")
        print("  1. 密钥填错 -> 检查 config/xunfei.json")
        print("  2. 网络不通 -> 检查能否访问 iat-api.xfyun.cn")
        print("  3. 服务未开通 -> 讯飞控制台确认已开通'语音听写'")
        sys.exit(1)

    if text:
        print(f"\n[成功] 识别结果: {text}")
        print("\n测试通过! voice_input 节点可以使用语音输入了。")
    else:
        print("\n[未识别] 没有检测到说话内容,请重试并确认麦克风正常。")


if __name__ == "__main__":
    main()
