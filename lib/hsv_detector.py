"""HSV 四色物体检测器（板端 / 本地通用）

改进自官方 color_detect_demo.py:
1. 遍历所有轮廓（官方 largest_contour 只取每色最大，会漏小球）
2. 四重过滤：面积 80~8000 + 圆形度>=0.5 + 深度有效>=0.5 + 深度范围 0.3~2.5m
3. 同位置多色去重：中心距离 < DEDUP_PX 时保留面积最大的检出
4. 相机坐标反投影：camera_info.K 内参 -> camera_point_m（相机坐标系，非 base_link）

用法（作为库）:
    from hsv_detector import detect_all
    annotated, detections, skipped = detect_all(color_bgr, depth_u16, camera_info_K_9)

用法（命令行，板端）:
    python3 hsv_detector.py            # 连 ROS 话题抓一帧检测
    python3 hsv_detector.py --loop 60  # 连续检测 60 秒（演示用）
"""
import argparse
import json
import os
import sys
import threading
import time

import cv2
import numpy as np

DRAW_COLORS = {
    "red": (0, 0, 255),
    "yellow": (0, 255, 255),
    "green": (0, 255, 0),
    "blue": (255, 0, 0),
}
# 调优版 HSV 范围（S 下限放宽以检出浅色球）
COLOR_RANGES = {
    "red": [([0, 100, 60], [10, 255, 255]), ([170, 100, 60], [180, 255, 255])],
    "yellow": [([14, 45, 75], [45, 255, 255])],
    "green": [([35, 65, 45], [90, 255, 255])],
    "blue": [([90, 50, 80], [135, 255, 255])],
}
# 面积范围: 目标=拳头大小黄色圆圈, 距车 <0.5m 时画面中可达 1~2.5 万 px,
# 上限放宽到 30000 避免近处大目标被滤掉; 下限 80 滤噪点
MIN_AREA, MAX_AREA = 80.0, 30000.0
# 圆形度下限: 目标圆从正面看 >=0.75, 场地黄色胶带(细长条)通常 <0.6;
# 0.6 可稳定检出圆度一般的黄圈而不误检胶带(实测定0.7会抖动丢帧)
MIN_CIRC = 0.6
MIN_DEPTH_RATIO = 0.5
# 深度范围过滤（Astra 有效 0.6~5m，目标距车 <0.5m，限 0.3~1.5m，滤掉远处地面黄色胶带）
DEPTH_MIN_MM, DEPTH_MAX_MM = 300.0, 1500.0
# 同位置多色去重阈值（像素中心距离）
DEDUP_PX = 15.0

COLOR_TOPIC = "/astra_camera/rgb/image_raw"
DEPTH_TOPIC = "/astra_camera/depth/image_raw"
CAMERA_INFO_TOPIC = "/astra_camera/depth/camera_info"


def image_rgb8(message):
    """sensor_msgs/Image (rgb8/bgr8) -> BGR ndarray（无需 cv_bridge）"""
    if message.encoding.lower() not in ("rgb8", "bgr8"):
        raise RuntimeError("unsupported color encoding: %s" % message.encoding)
    row_width = int(message.step)
    raw = np.frombuffer(message.data, dtype=np.uint8).reshape(message.height, row_width)
    image = raw[:, : message.width * 3].reshape(message.height, message.width, 3)
    if message.encoding.lower() == "rgb8":
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image.copy()


def image_depth16(message):
    """sensor_msgs/Image (16UC1) -> uint16 ndarray（单位 mm）"""
    if message.encoding.upper() not in ("16UC1", "MONO16"):
        raise RuntimeError("unsupported depth encoding: %s" % message.encoding)
    byte_order = ">u2" if message.is_bigendian else "<u2"
    values_per_row = int(message.step) // 2
    raw = np.frombuffer(message.data, dtype=np.dtype(byte_order)).reshape(
        message.height, values_per_row
    )
    return raw[:, : message.width].astype(np.uint16, copy=False)


def _contour_depth_stats(depth, contour):
    mask = np.zeros(depth.shape, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    total = int(np.count_nonzero(mask))
    valid = depth[(mask > 0) & (depth > 0)]
    valid_count = int(valid.size)
    return {
        "depth_mm": float(np.median(valid)) if valid_count >= 8 else None,
        "valid_pixels": valid_count,
        "valid_ratio": float(valid_count / total) if total else 0.0,
        "sample_pixels": total,
    }


def detect_all(color, depth, camera_info_K=None, frame_id=""):
    """主入口。color: BGR ndarray; depth: uint16 mm; camera_info_K: 9元素列表或None。
    返回 (annotated, detections, skipped)。
    detections 元素含: color/center_px/bbox_px/area_px/circularity/
    center_depth_mm/depth_valid_ratio/camera_point_m/frame_id
    """
    if color.shape[:2] != depth.shape[:2]:
        raise ValueError("RGB/depth size mismatch: %s vs %s" % (color.shape[:2], depth.shape[:2]))
    hsv = cv2.cvtColor(cv2.GaussianBlur(color, (5, 5), 0), cv2.COLOR_BGR2HSV)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    if camera_info_K is not None and len(camera_info_K) >= 6:
        fx, fy = float(camera_info_K[0]), float(camera_info_K[4])
        cx, cy = float(camera_info_K[2]), float(camera_info_K[5])
    else:
        fx = fy = cx = cy = 0.0
    annotated = color.copy()
    raw_detections = []
    skipped = []

    for name, ranges in COLOR_RANGES.items():
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lo, hi in ranges:
            mask = cv2.bitwise_or(
                mask, cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            )
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
        for c in contours:
            area = float(cv2.contourArea(c))
            if not (MIN_AREA <= area <= MAX_AREA):
                continue
            perimeter = float(cv2.arcLength(c, True))
            circ = (4.0 * np.pi * area / (perimeter * perimeter)) if perimeter else 0.0
            if circ < MIN_CIRC:
                continue
            moments = cv2.moments(c)
            if moments["m00"] <= 0:
                continue
            u = int(round(moments["m10"] / moments["m00"]))
            v = int(round(moments["m01"] / moments["m00"]))
            x, y, w, h = cv2.boundingRect(c)
            dstats = _contour_depth_stats(depth, c)
            depth_mm = dstats["depth_mm"]
            if dstats["valid_ratio"] < MIN_DEPTH_RATIO:
                continue
            if depth_mm is not None and not (DEPTH_MIN_MM <= depth_mm <= DEPTH_MAX_MM):
                skipped.append((name, [u, v], depth_mm, "out_of_range"))
                continue

            point_m = None
            if depth_mm is not None and fx > 0 and fy > 0:
                z_m = depth_mm / 1000.0
                point_m = {"x": (u - cx) * z_m / fx, "y": (v - cy) * z_m / fy, "z": z_m}
            raw_detections.append({
                "color": name,
                "center_px": [u, v],
                "bbox_px": [x, y, w, h],
                "area_px": area,
                "circularity": round(circ, 2),
                "center_depth_mm": depth_mm,
                "depth_valid_ratio": round(dstats["valid_ratio"], 2),
                "camera_point_m": point_m,
                "frame_id": frame_id,
            })

    # 同位置多色去重：中心距离 < DEDUP_PX 只保留面积最大的
    raw_detections.sort(key=lambda d: -d["area_px"])
    keep = []
    for d in raw_detections:
        dup = False
        for k in keep:
            du, dv = d["center_px"]
            ku, kv = k["center_px"]
            if (du - ku) ** 2 + (dv - kv) ** 2 < DEDUP_PX ** 2:
                dup = True
                break
        if not dup:
            keep.append(d)

    # 画框
    for d in keep:
        name = d["color"]
        draw = DRAW_COLORS[name]
        x, y, w, h = d["bbox_px"]
        u, v = d["center_px"]
        cv2.rectangle(annotated, (x, y), (x + w, y + h), draw, 2)
        label = "%s:%.0fmm" % (name, d["center_depth_mm"]) if d["center_depth_mm"] else name
        cv2.putText(annotated, label, (max(0, x + 2), min(annotated.shape[0] - 5, y + 18)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, draw, 2, cv2.LINE_AA)
        cv2.circle(annotated, (u, v), 4, draw, -1)
    return annotated, keep, skipped


def _ensure_ros_init():
    """确保 rospy 已初始化 (wait_for_message 依赖节点初始化, 幂等)。"""
    import rospy
    if not rospy.core.is_initialized():
        rospy.init_node("hsv_detector", anonymous=True, disable_signals=True)
    return rospy


# 持续订阅 + 缓存最新帧 (回调线程写, 主线程读, GIL 保证原子性)
_ROS_CACHE = {"color": None, "depth": None, "info": None}
_ROS_SUBS = None
_ROS_SUBS_LOCK = threading.Lock()


def _ros_worker_init():
    """惰性创建持续订阅, 缓存最新 RGB/Depth/CameraInfo 帧。替代每次 wait_for_message。"""
    global _ROS_SUBS
    with _ROS_SUBS_LOCK:
        if _ROS_SUBS is not None:
            return
        rospy = _ensure_ros_init()
        from sensor_msgs.msg import CameraInfo, Image

        def mk_cb(key):
            def cb(msg):
                _ROS_CACHE[key] = msg
            return cb

        _ROS_SUBS = [
            rospy.Subscriber(COLOR_TOPIC, Image, mk_cb("color"), queue_size=1),
            rospy.Subscriber(DEPTH_TOPIC, Image, mk_cb("depth"), queue_size=1),
            rospy.Subscriber(CAMERA_INFO_TOPIC, CameraInfo, mk_cb("info"), queue_size=1),
        ]
        # 等三路首帧到位 (最多 5 秒)
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if all(_ROS_CACHE[k] is not None for k in ("color", "depth", "info")):
                return
            time.sleep(0.05)
        raise RuntimeError("等待相机首帧超时: 未收到 RGB/Depth/CameraInfo")


def _grab_pair_ros(timeout_s=15.0):
    """从持续订阅缓存取最新一帧 RGB+Depth+camera_info。返回 (color, depth, K, frame_id)。"""
    _ros_worker_init()
    color_msg = _ROS_CACHE["color"]
    depth_msg = _ROS_CACHE["depth"]
    cam_info = _ROS_CACHE["info"]
    if color_msg is None or depth_msg is None or cam_info is None:
        return None
    color = image_rgb8(color_msg)
    depth = image_depth16(depth_msg)
    return color, depth, list(cam_info.K), cam_info.header.frame_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=float, default=0.0, help="连续检测秒数(0=单帧)")
    ap.add_argument("--interval", type=float, default=2.0, help="连续模式间隔秒")
    ap.add_argument("--out", default="/tmp/board_out", help="输出目录")
    args = ap.parse_args()

    import rospy
    rospy.init_node("hsv_detector", anonymous=True, disable_signals=True)
    os.makedirs(args.out, exist_ok=True)
    deadline = time.time() + args.loop if args.loop > 0 else time.time() + 3600.0
    first = True
    n_frames = 0

    while time.time() < deadline:
        try:
            color, depth, K, frame_id = _grab_pair_ros()
            n_frames += 1
            if first:
                print("RGB shape=%s | Depth shape=%s | frame_id=%s" % (
                    list(color.shape), list(depth.shape), frame_id), flush=True)
                first = False
            annotated, detections, skipped = detect_all(color, depth, K, frame_id)
            print("\n=== 帧#%d 检出 %d 个目标 ===" % (n_frames, len(detections)), flush=True)
            for r in sorted(detections, key=lambda d: -d["area_px"]):
                dm = ("%.0f" % r["center_depth_mm"]) if r["center_depth_mm"] else "None"
                print("  %-6s center=%s bbox=%s area=%.0f circ=%s depth=%smm ratio=%s cam3d=%s" % (
                    r["color"], r["center_px"], r["bbox_px"], r["area_px"],
                    r["circularity"], dm, r["depth_valid_ratio"], r["camera_point_m"]), flush=True)
            if skipped:
                print("  被深度范围过滤: %s" % [
                    "%s%s %.0fmm" % (s[0], s[1], s[2]) for s in skipped], flush=True)
            cv2.imwrite(os.path.join(args.out, "latest-hsv.jpg"), annotated)
            with open(os.path.join(args.out, "latest-hsv.json"), "w", encoding="utf-8") as f:
                json.dump({"frame": n_frames, "captured_unix_s": time.time(),
                           "image_shape": list(color.shape), "detections": detections,
                           "skipped": skipped}, f, ensure_ascii=False, indent=2)
            if args.loop <= 0:
                break
            time.sleep(args.interval)
        except Exception as e:
            print("检测异常: %s" % e, flush=True)
            time.sleep(0.5)
    print("已保存: %s/latest-hsv.jpg (.json)" % args.out, flush=True)


if __name__ == "__main__":
    main()
