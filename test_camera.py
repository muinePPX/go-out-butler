"""二维码识别 独立测试脚本(不依赖 Dora,在家先测通)

用法:
    1. pip install opencv-python pyzbar
    2. 打印几个二维码(内容: QR_WATER, QR_TOWEL, QR_KEYS 等)
    3. python test_camera.py

对着摄像头举二维码,看能否识别。也可测试本地图片:
    python test_camera.py 图片路径.png
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

from qr_recognizer import has_deps, recognize_qr_from_image, capture_and_recognize, list_cameras


def main():
    print("=" * 50)
    print("  二维码识别 - 独立测试")
    print("=" * 50)

    if not has_deps():
        print("\n[未安装] 缺少 opencv-python 或 pyzbar")
        print("请运行: pip install opencv-python pyzbar")
        sys.exit(1)

    print("\n[1] 探测可用摄像头...")
    cams = list_cameras()
    print(f"    可用摄像头索引: {cams if cams else '未找到'}")

    # 模式1: 识别本地图片
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        print(f"\n[2] 识别图片: {img_path}")
        results = recognize_qr_from_image(img_path)
        if results:
            print(f"\n[成功] 识别到 {len(results)} 个二维码:")
            for i, r in enumerate(results, 1):
                print(f"    {i}. {r}")
        else:
            print("\n[未识别] 图片中没有二维码,或图片路径不对")
        return

    # 模式2: 摄像头实时识别
    print("\n[2] 启动摄像头实时识别(对准二维码,10秒超时)")
    print("    期望识别的内容: QR_WATER, QR_TOWEL, QR_KEYS, QR_BADGE 等")
    print("    (对应 scenarios.json 里的 qr_code 字段)\n")

    cam_idx = cams[0] if cams else 0
    result = capture_and_recognize(camera_index=cam_idx, timeout_sec=10)

    if result:
        print(f"\n[成功] 识别到二维码: {result}")
        print("\n测试通过! camera_perception 节点可以使用二维码识别了。")
        print("\n提示: 现场把二维码贴在物品上,机器人相机识别后即可确认物品。")
    else:
        print("\n[未识别] 10秒内没识别到二维码。请:")
        print("  1. 确认摄像头正常(可用其他软件测试)")
        print("  2. 打印或手机显示二维码,对准摄像头")
        print("  3. 二维码内容应为: QR_WATER / QR_TOWEL / QR_KEYS 等")
        sys.exit(1)


if __name__ == "__main__":
    main()
