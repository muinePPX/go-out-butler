"""相机实时预览 + 二维码识别 (板端运行)

在电视上实时显示 Astra 相机画面,并实时识别二维码。
用途: 确认相机朝向 + 对准二维码 + 验证视觉链路。

用法(板端):
    run python3 /data/local/tmp/qr_live.py
退出: Ctrl+C
"""
import cv2
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image

bridge = CvBridge()
det = cv2.QRCodeDetector()
print("相机实时预览启动,电视上会显示画面", flush=True)
print("把二维码对准画面中央,识别到会打印并绿色框标记", flush=True)
print("按 Ctrl+C 退出", flush=True)


def cb(msg):
    try:
        img = bridge.imgmsg_to_cv2(msg, "bgr8")
        data, pts, _ = det.detectAndDecode(img)
        if data:
            print(f">>> 识别到二维码: {data}", flush=True)
            if pts is not None:
                pts = pts.astype(int).reshape(-1, 1, 2)
                cv2.polylines(img, [pts], True, (0, 255, 0), 3)
                cv2.putText(img, data, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 255, 0), 2)
        cv2.imshow("astra-camera", img)
        cv2.waitKey(1)
    except Exception as e:
        print(f"[err] {e}", flush=True)


if __name__ == "__main__":
    rospy.init_node("qr_live")
    rospy.Subscriber("/astra_camera/rgb/image_raw", Image, cb)
    rospy.spin()
