"""深度相机感知节点 - 双模式识别 (AprilTag | HSV 颜色)

收到 camera_cmd -> 取相机帧 -> 识别 -> 输出 item_result

模式选择（camera_cmd 字段）:
  - mode="apriltag" (默认, 兼容旧流程): 识别 target apriltag_id / qr_code
  - mode="color": 识别 target_colors 指定的颜色物体(red/yellow/green/blue),
                  HSV 检测器输出 3D 相机坐标 camera_point_m 供机械臂抓取

现场相机: Astra Pro Plus (ROS 话题 /astra_camera/rgb/image_raw + depth)
环境变量:
  CAMERA_SOURCE = ros | opencv  (默认 opencv)
  CAMERA_INDEX  = 摄像头编号    (opencv 模式)
  CAMERA_TOPIC  = RGB话题名     (ros 模式, 默认 /astra_camera/rgb/image_raw)
  DEPTH_TOPIC   = 深度话题名    (ros 模式, 默认 /astra_camera/depth/image_raw)
  CAMERA_TIMEOUT= 识别超时秒     (默认 8)
"""
import json
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pyarrow as pa
from dora import Node

node = Node()

# ---- 相机来源配置 ----
CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "opencv")
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAMERA_TOPIC = os.environ.get("CAMERA_TOPIC", "/astra_camera/rgb/image_raw")
DEPTH_TOPIC = os.environ.get("DEPTH_TOPIC", "/astra_camera/depth/image_raw")
CAMERA_INFO_TOPIC = os.environ.get("CAMERA_INFO_TOPIC", "/astra_camera/depth/camera_info")
# 目标在车侧边 <0.5m, 单圈 360° 内必扫到: 角速度 0.45 rad/s(约26°/s, 一圈约14s),
# 超时 18s 即放弃, 避免长时间原地转圈
SCAN_TIMEOUT = float(os.environ.get("CAMERA_TIMEOUT", "18"))
SCAN_WZ = float(os.environ.get("SCAN_WZ", "0.45"))

print(f"[camera_perception] 感知节点已启动 (双模式: AprilTag|HSV颜色, 相机源: {CAMERA_SOURCE})", flush=True)


def _ensure_ros_init():
    """确保 rospy 已初始化 (wait_for_message 依赖节点初始化, 幂等)。"""
    import rospy
    if not rospy.core.is_initialized():
        rospy.init_node("camera_perception", anonymous=True)
    return rospy


def _import_ros():
    rospy = _ensure_ros_init()
    from sensor_msgs.msg import CameraInfo, Image
    return rospy, Image, CameraInfo


def grab_frame():
    """取一帧彩色图(BGR ndarray)。失败返回 None。"""
    if CAMERA_SOURCE == "ros":
        try:
            rospy = _ensure_ros_init()
            from sensor_msgs.msg import Image
            msg = rospy.wait_for_message(CAMERA_TOPIC, Image, timeout=5)
            from hsv_detector import image_rgb8
            return image_rgb8(msg)
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


def grab_rgbd():
    """ROS 模式取一帧 RGB+Depth+camera_info。返回 (color, depth, K, frame_id) 或 None。"""
    if CAMERA_SOURCE != "ros":
        return None
    try:
        from hsv_detector import image_depth16, image_rgb8
        rospy, Image, CameraInfo = _import_ros()
        color_msg = rospy.wait_for_message(CAMERA_TOPIC, Image, timeout=5)
        depth_msg = rospy.wait_for_message(DEPTH_TOPIC, Image, timeout=5)
        cam_info = rospy.wait_for_message(CAMERA_INFO_TOPIC, CameraInfo, timeout=5)
        color = image_rgb8(color_msg)
        depth = image_depth16(depth_msg)
        return color, depth, list(cam_info.K), cam_info.header.frame_id
    except Exception as e:
        print(f"[camera_perception] grab_rgbd 失败: {e}", flush=True)
        return None


# ==================== AprilTag 模式（兼容旧流程） ====================
def perceive_apriltag(item, target_id, timeout_sec=SCAN_TIMEOUT):
    from apriltag_recognizer import detect_apriltags
    result = {"found": False, "item": item, "apriltag_id": target_id,
              "confidence": None, "error": None}
    if target_id is None:
        result["error"] = "未指定目标 AprilTag ID"
        return result
    print(f"[camera_perception] [apriltag] 识别目标 id={target_id} (最长{timeout_sec:.0f}s)", flush=True)
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
    else:
        result["error"] = "视野中未检测到目标 AprilTag"
    return result


# ==================== HSV 颜色模式（验证过的方案） ====================
_SCAN_PUB = {"pub": None}  # 缓存 /cmd_vel Publisher (旋转扫描用)
_SCAN_STOP = None          # threading.Event: 停止旋转扫描线程


def _publish_cmd_vel(wz):
    """发布一条 /cmd_vel (wz=角速度 rad/s)。异常仅打日志不影响识别流程。"""
    try:
        from geometry_msgs.msg import Twist
        rospy = _ensure_ros_init()
        if _SCAN_PUB["pub"] is None:
            _SCAN_PUB["pub"] = rospy.Publisher("/cmd_vel", Twist, queue_size=1)
        msg = Twist()
        msg.linear.x = 0.0
        msg.linear.y = 0.0
        msg.angular.z = float(wz)
        _SCAN_PUB["pub"].publish(msg)
    except Exception as e:
        print(f"[camera_perception] cmd_vel 发送失败: {e}", flush=True)


def _start_scan_spin(wz):
    """后台线程持续发布角速度 (0.2s 间隔), 保证底盘指令不因取帧耗时中断(底盘 0.5s 超时)。"""
    global _SCAN_STOP
    _ensure_ros_init()  # 先完成 ROS 初始化, 避免后台线程竞态 (init_node 未完成时发布会报错)
    _SCAN_STOP = threading.Event()

    def spin():
        while not _SCAN_STOP.is_set():
            _publish_cmd_vel(wz)
            time.sleep(0.2)

    t = threading.Thread(target=spin, daemon=True, name="scan-spin")
    t.start()
    return t


def _stop_scan_spin(spin_thread):
    """停止旋转线程并发零速兜底停车。"""
    if _SCAN_STOP is not None:
        _SCAN_STOP.set()
    if spin_thread is not None:
        spin_thread.join(timeout=0.5)
    _publish_cmd_vel(0.0)


def perceive_color(item, target_colors, timeout_sec=SCAN_TIMEOUT):
    """识别目标颜色物体，输出 3D 相机坐标。target_colors: 如 ['yellow']。
    识别期间底盘持续原地旋转 (旋转扫描), 扫到目标立即停转。"""
    from hsv_detector import detect_all
    result = {"found": False, "item": item, "apriltag_id": None,
              "confidence": None, "error": None,
              "camera_point_m": None, "center_px": None,
              "center_depth_mm": None, "detections": []}
    if not target_colors:
        result["error"] = "未指定目标颜色"
        return result
    print(f"[camera_perception] [color] 旋转扫描目标颜色 {target_colors} (最长{timeout_sec:.0f}s, 角速度 {SCAN_WZ:.2f} rad/s)", flush=True)
    start = time.time()
    matched = None
    spin = _start_scan_spin(SCAN_WZ)          # 启动持续旋转
    try:
        while time.time() - start < timeout_sec:
            rgbd = grab_rgbd()
            if rgbd is None:
                time.sleep(0.1)
                continue
            color, depth, K, frame_id = rgbd
            annotated, detections, _ = detect_all(color, depth, K, frame_id)
            # 只认高圆形度的真目标 (滤掉场地黄色边缘等非圆干扰), 优先最圆的
            candidates = [d for d in detections
                          if d["color"] in target_colors and d["circularity"] >= 0.7]
            if candidates:
                candidates.sort(key=lambda d: (d["circularity"], d["area_px"]), reverse=True)
                matched = candidates[0]
                print(f"[camera_perception] [color] 候选: {[(d['color'], d['center_px'], d['center_depth_mm']) for d in candidates]}", flush=True)
                break
    finally:
        _stop_scan_spin(spin)                 # 找到/超时/异常均停转
    if matched is not None:
        result["found"] = True
        result["confidence"] = matched["circularity"]
        result["color"] = matched["color"]
        result["center_px"] = matched["center_px"]
        result["center_depth_mm"] = matched["center_depth_mm"]
        result["camera_point_m"] = matched["camera_point_m"]
        result["bbox_px"] = matched["bbox_px"]
        result["detections"] = detections
    else:
        result["error"] = f"视野中未检测到目标颜色 {target_colors}"
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
        item = cmd.get("item", "unknown")
        mode = cmd.get("mode", "apriltag")
        target_colors = cmd.get("target_colors") or []
        target_id = cmd.get("apriltag_id")
        if target_id is None and cmd.get("qr_code") is not None:
            qr = str(cmd["qr_code"])
            target_id = int(qr) if qr.isdigit() else None
        index = cmd.get("index", -1)
    except Exception as e:
        print(f"[camera_perception] 无效 camera_cmd 已忽略: {e}", flush=True)
        node.send_output("item_result", pa.array([json.dumps(
            {"found": False, "item": None, "apriltag_id": None, "index": -1,
             "error": f"invalid camera_cmd: {e}"}, ensure_ascii=False)]))
        continue

    print(f"[camera_perception] 收到识别指令: {item} (mode={mode}, 序号 {index})", flush=True)

    # ---- 执行识别; 异常兜底 ----
    t0 = time.monotonic()
    try:
        if mode == "color":
            result = perceive_color(item, target_colors)
        else:
            result = perceive_apriltag(item, target_id)
    except Exception as e:
        traceback.print_exc()
        result = {"found": False, "item": item, "apriltag_id": target_id,
                  "confidence": None, "error": f"{type(e).__name__}: {e}"}
    elapsed = time.monotonic() - t0

    # ---- 上报结果, 回显 index 便于调度器核对 ----
    item_result = {
        "found": result.get("found", False),
        "item": item,
        "mode": mode,
        "apriltag_id": result.get("apriltag_id"),
        "index": index,
        "confidence": result.get("confidence"),
        "elapsed": round(elapsed, 2),
        "error": result.get("error"),
        "color": result.get("color"),
        "center_px": result.get("center_px"),
        "center_depth_mm": result.get("center_depth_mm"),
        "camera_point_m": result.get("camera_point_m"),
        "bbox_px": result.get("bbox_px"),
        "detections": result.get("detections", []),
    }
    if result.get("found"):
        print(f"[camera_perception] 已识别 {item} (mode={mode}, 耗时 {elapsed:.1f}s, "
              f"点={item_result['camera_point_m']})", flush=True)
    else:
        print(f"[camera_perception] 未找到 {item} ({item_result['error']})", flush=True)
    node.send_output("item_result", pa.array([json.dumps(item_result, ensure_ascii=False)]))
