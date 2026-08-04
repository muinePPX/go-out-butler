"""深度相机感知节点 - AprilTag 识别物品

收到 camera_cmd(含物品名+目标AprilTag ID) -> 取相机帧 -> 检测 AprilTag
-> 匹配目标ID则 found=True -> 输出 item_result

现场相机: Astra Pro Plus(订阅 ROS 话题) 或 OpenCV 读视频设备
识别方式: AprilTag (tag36h11 等, 用 OpenCV cv2.aruco)
兼容: camera_cmd 里可用 apriltag_id(新) 或 qr_code(旧, 数字ID) 指定目标

环境变量:
  CAMERA_SOURCE = ros | opencv  (默认 opencv)
  CAMERA_INDEX  = 摄像头编号    (opencv 模式)
  CAMERA_TOPIC  = ROS话题名     (ros 模式, 默认 /astra_camera/rgb/image_raw)
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pyarrow as pa
from dora import Node
from apriltag_recognizer import detect_apriltags

node = Node()

# ---- 相机来源配置 ----
CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "opencv")
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAMERA_TOPIC = os.environ.get("CAMERA_TOPIC", "/astra_camera/rgb/image_raw")
SCAN_TIMEOUT = float(os.environ.get("CAMERA_TIMEOUT", "8"))

print(f"[camera_perception] 感知节点已启动 (AprilTag识别, 相机源: {CAMERA_SOURCE})", flush=True)


def grab_frame():
    """取一帧彩色图(BGR ndarray)。失败返回 None。"""
    if CAMERA_SOURCE == "ros":
        try:
            import rospy
            from cv_bridge import CvBridge
            from sensor_msgs.msg import Image
            bridge = CvBridge()
            msg = rospy.wait_for_message(CAMERA_TOPIC, Image, timeout=5)
            return bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception:
            return None
    try:
        import cv2
        cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        return frame if ret else None
    except Exception:
        return None


def perceive(item, target_id, timeout_sec=SCAN_TIMEOUT):
    """在 timeout_sec 内识别目标 AprilTag。找到返回 found=True。"""
    result = {"found": False, "item": item, "apriltag_id": target_id,
              "confidence": None, "error": None}

    if target_id is None:
        result["error"] = "未指定目标 AprilTag ID"
        return result

    print(f"[camera_perception] 开始识别目标 AprilTag id={target_id} "
          f"(最长{timeout_sec:.0f}秒)", flush=True)
    start = time.time()
    matched = None

    while time.time() - start < timeout_sec:
        frame = grab_frame()
        if frame is None:
            time.sleep(0.1)
            continue
        tags = detect_apriltags(frame)
        for t in tags:
            print(f"[camera_perception] 检测到 AprilTag: family={t['family']} id={t['id']}", flush=True)
            if t["id"] == target_id:
                matched = t
                break
        if matched is not None:
            break

    if matched is not None:
        result["found"] = True
        result["confidence"] = 0.95
        print(f"[camera_perception] 目标命中! AprilTag id={target_id}", flush=True)
    else:
        result["error"] = "视野中未检测到目标 AprilTag"
        print(f"[camera_perception] 未找到 AprilTag id={target_id}", flush=True)
    return result


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "camera_cmd":
        continue

    # ---- 解析识别命令; 异常时回复未找到, 避免调度器死等 ----
    try:
        if event["value"] is None:
            raise ValueError("empty value")
        cmd = json.loads(event["value"].to_pylist()[0])
        item = cmd["item"]
        # 兼容: 优先 apriltag_id, 其次 qr_code(按数字ID处理)
        target_id = cmd.get("apriltag_id")
        if target_id is None and cmd.get("qr_code") is not None:
            qr = str(cmd["qr_code"])
            if qr.isdigit():
                target_id = int(qr)
            else:
                target_id = None
        index = cmd.get("index", -1)
    except Exception as e:
        print(f"[camera_perception] 无效 camera_cmd 已忽略: {e}", flush=True)
        node.send_output("item_result", pa.array([json.dumps(
            {"found": False, "item": None, "apriltag_id": None, "index": -1,
             "error": f"invalid camera_cmd: {e}"}, ensure_ascii=False)]))
        continue

    print(f"[camera_perception] 收到识别指令: {item} (AprilTag ID: {target_id}, 序号 {index})", flush=True)

    # ---- 执行识别; 异常兜底 ----
    t0 = time.monotonic()
    try:
        result = perceive(item, target_id)
    except Exception as e:
        traceback.print_exc()
        result = {"found": False, "item": item, "apriltag_id": target_id,
                  "confidence": None, "error": f"{type(e).__name__}: {e}"}
    elapsed = time.monotonic() - t0

    if result["found"]:
        print(f"[camera_perception] 已识别 {item} (AprilTag {target_id}, 耗时 {elapsed:.1f}s)", flush=True)
    else:
        print(f"[camera_perception] 未找到 {item} ({result['error']})", flush=True)

    # ---- 上报结果, 回显 index 便于调度器核对 ----
    item_result = {
        "found": result["found"],
        "item": item,
        "apriltag_id": result["apriltag_id"],
        "index": index,
        "confidence": result["confidence"],
        "elapsed": round(elapsed, 2),
        "error": result["error"],
    }
    node.send_output("item_result", pa.array([json.dumps(item_result, ensure_ascii=False)]))
