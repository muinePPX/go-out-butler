"""二维码识别工具模块

用 OpenCV 读画面 + pyzbar 解码二维码。
可被 camera_perception 节点和 test_camera.py 测试脚本复用。

依赖: opencv-python, pyzbar (见 requirements.txt)
pyzbar 在 Windows 上需要 zbar dll,安装 pyzbar 时通常自带。
若报错" Unable to find zbar shared library",安装 zbar:
  Windows: pip install pyzbar (自带 dll) 或下载 zbar.dll
  Linux: sudo apt install libzbar0
"""
from __future__ import annotations

try:
    from pyzbar.pyzbar import decode as _pyzbar_decode
    import cv2
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


def has_deps():
    """是否安装了 opencv 和 pyzbar。"""
    return _HAS_DEPS


def recognize_qr(frame):
    """从一帧画面(BGR ndarray)识别所有二维码。

    返回列表,每项 {"data": 解码内容, "rect": (x,y,w,h)}。
    无二维码返回空列表。
    """
    if not _HAS_DEPS:
        return []
    # pyzbar 需要灰度图,但传 BGR 也能处理
    results = []
    for obj in _pyzbar_decode(frame):
        data = obj.data.decode("utf-8", errors="replace")
        rect = (obj.rect.left, obj.rect.top, obj.rect.width, obj.rect.height)
        results.append({"data": data, "rect": rect})
    return results


def recognize_qr_from_image(image_path):
    """从图片文件识别二维码。返回解码内容列表。"""
    if not _HAS_DEPS:
        return []
    img = cv2.imread(image_path)
    if img is None:
        return []
    return [r["data"] for r in recognize_qr(img)]


def list_cameras(max_index=5):
    """探测可用的摄像头索引列表(用于现场选择 Orbbec 相机)。"""
    if not _HAS_DEPS:
        return []
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available


def capture_and_recognize(camera_index=0, timeout_sec=10):
    """打开相机,持续读帧识别二维码,直到识别到或超时。

    返回第一个识别到的二维码内容,超时返回 None。
    """
    if not _HAS_DEPS:
        return None
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    start = __import__("time").time()
    result = None
    import time as _t
    while _t.time() - start < timeout_sec:
        ret, frame = cap.read()
        if not ret:
            continue
        qrs = recognize_qr(frame)
        if qrs:
            result = qrs[0]["data"]
            break
    cap.release()
    return result
