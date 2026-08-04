"""AprilTag 识别工具模块

用 OpenCV cv2.aruco 检测 AprilTag(机器人领域常用视觉标签)。
AprilTag 的识别结果是 数字 ID(不是字符串), 区别于 QR 二维码。

支持 family: tag36h11(最常用), tag25h9, tag16h5
用法:
    from apriltag_recognizer import detect_apriltags
    tags = detect_apriltags(frame)
    # tags: [{"family":"tag36h11","id":0}, ...]
"""
from __future__ import annotations

import cv2


# OpenCV 的 AprilTag 字典映射
_FAMILY_MAP = {
    "tag36h11": cv2.aruco.DICT_APRILTAG_36h11,
    "tag25h9": cv2.aruco.DICT_APRILTAG_25h9,
    "tag16h5": cv2.aruco.DICT_APRILTAG_16h5,
}


def detect_apriltags(frame, families=("tag36h11", "tag25h9", "tag16h5")):
    """从一帧画面(BGR ndarray)检测所有 AprilTag。

    返回列表,每项 {"family": str, "id": int, "corners": ndarray}。
    无标签返回空列表。
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    results = []
    for fam in families:
        if fam not in _FAMILY_MAP:
            continue
        dictionary = cv2.aruco.getPredefinedDictionary(_FAMILY_MAP[fam])
        detector = cv2.aruco.ArucoDetector(dictionary)
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is not None:
            for i, mid in enumerate(ids.flatten()):
                results.append({"family": fam, "id": int(mid), "corners": corners[i]})
    return results


def detect_apriltags_from_image(image_path, families=("tag36h11", "tag25h9", "tag16h5")):
    """从图片文件检测 AprilTag,返回 [(family, id), ...]。"""
    img = cv2.imread(image_path)
    if img is None:
        return []
    return [(t["family"], t["id"]) for t in detect_apriltags(img, families=families)]
