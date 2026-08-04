"""标签识别 (无显示模式, 板端后台运行) - 同时支持 QR 二维码 和 AprilTag

订阅 Astra 相机流, 实时识别 QR + AprilTag, 结果打印到 stdout/日志。
用途: 后台运行, 用户移动标签, 观察日志判断相机视野内是否识别到。

用法(板端后台):
    nohup run python3 /data/local/tmp/qr_scan.py > /data/local/tmp/qr_scan.log 2>&1 &
"""
import os
import sys

sys.path.insert(0, "/data/local/tmp")

import cv2
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image

from apriltag_recognizer import detect_apriltags

bridge = CvBridge()
qr_det = cv2.QRCodeDetector()
print("标签识别已启动(QR + AprilTag), 等待标签进入视野...", flush=True)


def cb(msg):
    try:
        img = bridge.imgmsg_to_cv2(msg, "bgr8")
        # 1. QR 二维码
        data, pts, _ = qr_det.detectAndDecode(img)
        if data:
            print(f">>> QR识别到: {data}", flush=True)
        # 2. AprilTag
        tags = detect_apriltags(img)
        for t in tags:
            print(f">>> AprilTag识别到: family={t['family']} id={t['id']}", flush=True)
    except Exception:
        pass


if __name__ == "__main__":
    rospy.init_node("tag_scan")
    rospy.Subscriber("/astra_camera/rgb/image_raw", Image, cb)
    rospy.spin()
