"""视觉伺服对齐节点（示教抓取路线的核心闭环）

范式: 收到 servo_cmd -> 循环抓帧检测目标颜色 -> 像素偏差 -> 底盘速度(servo_vel)
      横向+深度均收敛并稳定 N 帧 -> 输出 servo_result(aligned=true)
      超时 -> servo_result(aligned=false)

与 camera_perception 的关系:
  camera_perception 负责"找到目标"(一次性), 本节点负责"把目标对齐到示教抓取位"(闭环)。
  对齐完成后由 task_scheduler 发 arm_cmd 执行示教抓取。

输入(servo_cmd):  {item, index, target_colors:[...], grasp_depth_m, servo_params:{...}}
输出(servo_vel):  {linear_x, linear_y, target_lost, aligned, dx_m, dz_m, info}
输出(servo_result):{aligned, item, index, elapsed, error, params}

环境变量:
  CAMERA_SOURCE   = ros | opencv (视觉伺服需要深度, 默认 ros)
  SERVO_TIMEOUT   = 对齐超时秒    (默认 40)
  SERVO_TICK      = 控制周期秒    (默认 0.2, 即 5Hz)
  相机话题沿用 hsv_detector 默认: /astra_camera/rgb/image_raw 等
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pyarrow as pa
from dora import Node

node = Node()

CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "ros")
SERVO_TIMEOUT = float(os.environ.get("SERVO_TIMEOUT", "40"))
SERVO_TICK = float(os.environ.get("SERVO_TICK", "0.2"))
SEARCH_WZ = float(os.environ.get("SERVO_SEARCH_WZ", "0.30"))  # 目标丢失时旋转搜索角速度
# 目标丢失后旋转搜索的累计时长上限: 目标在车侧边 <0.5m, 6s*0.30rad/s≈100°足够扫过,
# 超时即放弃本次对齐, 避免伺服阶段长时间原地转圈
SEARCH_MAX_SEC = float(os.environ.get("SERVO_SEARCH_MAX_SEC", "6.0"))

print(f"[visual_servoing] 节点已启动 (相机源={CAMERA_SOURCE}, 超时={SERVO_TIMEOUT}s, 周期={SERVO_TICK}s)", flush=True)


def grab_rgbd():
    """抓一帧 RGB+Depth+camera_info。返回 (color, depth, K, frame_id) 或 None。"""
    if CAMERA_SOURCE != "ros":
        print("[visual_servoing] 视觉伺服需要深度相机, 请设置 CAMERA_SOURCE=ros", flush=True)
        return None
    try:
        from hsv_detector import _grab_pair_ros
        return _grab_pair_ros(timeout_s=5.0)
    except Exception as e:
        print(f"[visual_servoing] 抓帧失败: {e}", flush=True)
        return None


def run_servo(cmd, timeout_s):
    """对齐闭环主体。返回 servo_result dict。"""
    item = cmd.get("item", "unknown")
    index = cmd.get("index", -1)
    target_colors = cmd.get("target_colors") or []
    servo_params = cmd.get("servo_params") or {}
    if not target_colors:
        return {"aligned": False, "item": item, "index": index,
                "elapsed": 0.0, "error": "未指定目标颜色"}

    from visual_servo import VisualServoController
    from hsv_detector import detect_all

    controller = None
    start = time.monotonic()
    last_zero_vel = 0.0
    frames_seen = 0
    aligned_info = None
    lost_count = 0  # 连续丢失帧数 (用于触发旋转搜索)
    lost_start = None  # 目标丢失开始时间戳 (旋转搜索时长计时)
    lost_timeout = False  # 旋转搜索超时标志 (放弃本次对齐)

    print(f"[visual_servoing] 开始对齐 {item} 颜色={target_colors} "
          f"对准距离={servo_params.get('grasp_depth_m', '默认0.65')}m (最长{timeout_s:.0f}s)", flush=True)

    while time.monotonic() - start < timeout_s:
        rgbd = grab_rgbd()
        if rgbd is None:
            time.sleep(0.05)
            continue
        color, depth, K, frame_id = rgbd
        fx, fy, cx, cy = float(K[0]), float(K[4]), float(K[2]), float(K[5])
        if controller is None:
            # 首次取到内参后创建控制器; 之后内参变动只更新数值
            controller = VisualServoController(fx, fy, cx, cy, servo_params)
        else:
            controller.fx, controller.fy = fx, fy
            controller.cx, controller.cy = cx, cy

        annotated, detections, _ = detect_all(color, depth, K, frame_id)
        # 只认高圆形度的真目标 (滤掉场地黄色边缘等非圆干扰)
        candidates = [d for d in detections
                      if d["color"] in target_colors and d["circularity"] >= 0.7]
        frames_seen += 1

        if not candidates:
            # 目标丢失: 短暂原地搜索, 仍找不到则缓慢旋转扫描 (底盘角速度由 nav_control 转发)
            lost_count += 1
            if lost_start is None:
                lost_start = time.monotonic()
            if lost_count % 5 == 1:
                print(f"[visual_servoing] lost#{lost_count} 视野概览: "
                      f"{[(d['color'], d['circularity'], int(d['area_px']), d['center_depth_mm']) for d in detections][:10]}",
                      flush=True)
            # 旋转搜索累计超时: 目标在车侧边 <0.5m, 6s*0.30rad/s≈100°足够扫过, 超时即放弃本次对齐
            if time.monotonic() - lost_start > SEARCH_MAX_SEC:
                print(f"[visual_servoing] 目标丢失旋转搜索超过 {SEARCH_MAX_SEC:.0f}s, 放弃对齐 {item}", flush=True)
                lost_timeout = True
                break
            searching = lost_count > 3
            now = time.monotonic()
            if now - last_zero_vel >= SERVO_TICK:
                node.send_output("servo_vel", pa.array([json.dumps(
                    {"linear_x": 0.0, "linear_y": 0.0,
                     "wz": SEARCH_WZ if searching else 0.0,
                     "target_lost": True,
                     "aligned": False, "item": item, "searching": searching}, ensure_ascii=False)]))
                last_zero_vel = now
            time.sleep(SERVO_TICK)
            continue

        # 目标重新出现: 先停转 (从旋转搜索切回对齐), 再伺服
        if lost_count > 0:
            node.send_output("servo_vel", pa.array([json.dumps(
                {"linear_x": 0.0, "linear_y": 0.0, "wz": 0.0,
                 "target_lost": False, "aligned": False, "item": item},
                ensure_ascii=False)]))
            lost_count = 0
            lost_start = None
            time.sleep(0.3)  # 给底盘停稳时间, 避免旋转惯性影响伺服
            continue

        # 同色多个时优先最圆的
        best = max(candidates, key=lambda d: (d["circularity"], d["area_px"]))
        u, v = best["center_px"]
        depth_m = (best["center_depth_mm"] / 1000.0) if best["center_depth_mm"] else None
        vel, info = controller.step([u, v], depth_m, color.shape[1])

        out = {
            "linear_x": vel["linear_x"],
            "linear_y": vel["linear_y"],
            "target_lost": False,
            "aligned": info["converged"],
            "item": item,
            "color": best["color"],
            "dx_m": round(info["dx_m"], 4) if info["dx_m"] is not None else None,
            "dz_m": round(info["dz_m"], 4) if info["dz_m"] is not None else None,
            "stable": controller.stable_count,
        }
        node.send_output("servo_vel", pa.array([json.dumps(out, ensure_ascii=False)]))
        if info["converged"]:
            aligned_info = out
            print(f"[visual_servoing] 对齐完成: {item} 颜色={best['color']} "
                  f"深度={depth_m:.3f}m 帧数={frames_seen}", flush=True)
            break
        time.sleep(SERVO_TICK)

    # 收尾: 无论成败都发零速, 让底盘停下
    node.send_output("servo_vel", pa.array([json.dumps(
        {"linear_x": 0.0, "linear_y": 0.0, "target_lost": False,
         "aligned": False, "item": item, "final": True}, ensure_ascii=False)]))

    elapsed = time.monotonic() - start
    if aligned_info is not None:
        return {"aligned": True, "item": item, "index": index,
                "elapsed": round(elapsed, 2), "error": None,
                "color": aligned_info["color"],
                "dx_m": aligned_info["dx_m"], "dz_m": aligned_info["dz_m"],
                "frames_seen": frames_seen}
    if lost_timeout:
        error = f"目标丢失搜索超时({SEARCH_MAX_SEC:.0f}s), 检出帧数={frames_seen}"
    else:
        error = f"对齐超时({timeout_s:.0f}s), 检出帧数={frames_seen}"
    return {"aligned": False, "item": item, "index": index,
            "elapsed": round(elapsed, 2), "error": error}


for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] != "servo_cmd":
        continue

    # ---- 解析对齐命令; 异常时直接回复失败, 避免调度器死等 ----
    try:
        if event["value"] is None:
            raise ValueError("empty value")
        cmd = json.loads(event["value"].to_pylist()[0])
        item = cmd.get("item", "unknown")
        index = cmd.get("index", -1)
        timeout_s = float(cmd.get("timeout", SERVO_TIMEOUT))
    except Exception as e:
        print(f"[visual_servoing] 无效 servo_cmd 已忽略: {e}", flush=True)
        node.send_output("servo_result", pa.array([json.dumps(
            {"aligned": False, "item": None, "index": -1,
             "error": f"invalid servo_cmd: {e}"}, ensure_ascii=False)]))
        continue

    print(f"[visual_servoing] 收到对齐指令: {item} (序号 {index})", flush=True)
    try:
        result = run_servo(cmd, timeout_s)
    except Exception as e:
        print(f"[visual_servoing] 对齐异常: {e}", flush=True)
        import traceback
        traceback.print_exc()
        result = {"aligned": False, "item": item, "index": index,
                  "elapsed": 0.0, "error": f"{type(e).__name__}: {e}"}
    node.send_output("servo_result", pa.array([json.dumps(result, ensure_ascii=False)]))
