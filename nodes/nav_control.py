"""导航控制节点 - 真实底盘控制 (cmd_vel + odom 里程计闭环)

输入:
  nav_cmd    {"waypoint": str, "item": str}   导航指令
  servo_vel  {"linear_x": float, "linear_y": float, "final": bool, "target_lost": bool}
                                            视觉伺服对齐阶段的速度(转发到底盘)
输出:
  nav_done   {"success": bool, "waypoint": str, "item": str}

底盘接口:
  发布  /cmd_vel (geometry_msgs/Twist)   -- 底盘驱动订阅, 0.5s 无指令自动停车, 需 >=2Hz 持续发布
  订阅  /odom   (nav_msgs/Odometry)      -- 里程计位置/姿态

限制:
  最大线速 0.20 m/s, 最大角速 0.50 rad/s (驱动层硬限)

导航策略 (无 move_base 时的手搓闭环):
  1) 读 odom 当前位置 (x, y, yaw)
  2) 计算目标方位角, 原地旋转对准目标方向 (角速度闭环)
  3) 沿当前朝向直行, 以里程计位移判断到达 (线速度闭环)
  4) 到位停车, 回 nav_done

坐标约定: waypoints.json 使用 odom 系坐标 (point_door=(0,0) 与 odom 原点一致)。
环境变量:
  WAYPOINTS_FILE  点位配置文件 (默认 ../config/waypoints.json 相对本文件)
  NAV_LIN_MAX     直行限速 m/s  (默认 0.15)
  NAV_ANG_MAX     转向限速 rad/s (默认 0.35)
  NAV_DIST_TOL    到位距离容差 m (默认 0.08, 视觉伺服负责末段对齐)
  NAV_ANG_TOL     对准角度容差 rad (默认 0.05)
  NAV_TIMEOUT     单段导航超时 s (默认 12)
"""
import json
import math
import os
import threading
import time
import traceback

import pyarrow as pa
from dora import Node

node = Node()
print("[nav_control] 导航节点启动 (真实底盘: /cmd_vel + /odom 闭环)", flush=True)

# ---- 参数 ----
_WAYPOINTS_FILE = os.environ.get(
    "WAYPOINTS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waypoints.json"),
)
NAV_LIN_MAX = float(os.environ.get("NAV_LIN_MAX", "0.15"))
NAV_ANG_MAX = float(os.environ.get("NAV_ANG_MAX", "0.35"))
NAV_DIST_TOL = float(os.environ.get("NAV_DIST_TOL", "0.08"))
NAV_ANG_TOL = float(os.environ.get("NAV_ANG_TOL", "0.05"))
NAV_TIMEOUT = float(os.environ.get("NAV_TIMEOUT", "12"))
CTRL_HZ = 10.0  # 指令发布频率, 远高于驱动 0.5s 超时阈值

# ---- ROS 初始化 ----
def _ensure_ros_init():
    import rospy
    if not rospy.core.is_initialized():
        rospy.init_node("nav_control", anonymous=True)
    return rospy


_rospy = _ensure_ros_init()
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

# ---- odom 订阅: 回调写最新位姿, 主流程读取 (线程安全) ----
_latest = {"x": 0.0, "y": 0.0, "yaw": 0.0, "stamp": 0.0}
_lock = threading.Lock()


def _odom_cb(msg):
    q = msg.pose.pose.orientation
    # 四元数 -> yaw
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    yaw = math.atan2(siny, cosy)
    with _lock:
        _latest["x"] = msg.pose.pose.position.x
        _latest["y"] = msg.pose.pose.position.y
        _latest["yaw"] = yaw
        _latest["stamp"] = time.time()


_odom_sub = _rospy.Subscriber("/odom", Odometry, _odom_cb, queue_size=1)
_cmd_pub = _rospy.Publisher("/cmd_vel", Twist, queue_size=1)

# ---- 发布速度 (保持 >=2Hz, 驱动 0.5s 超时自动停车) ----
_last_pub = {"vx": 0.0, "vy": 0.0, "wz": 0.0}
_keep_lock = threading.Lock()


def publish_vel(vx, vy, wz):
    twist = Twist()
    twist.linear.x = max(-0.2, min(0.2, float(vx)))
    twist.linear.y = max(-0.2, min(0.2, float(vy)))
    twist.angular.z = max(-0.5, min(0.5, float(wz)))
    _cmd_pub.publish(twist)
    with _keep_lock:
        _last_pub["vx"], _last_pub["vy"], _last_pub["wz"] = vx, vy, wz


def stop():
    publish_vel(0.0, 0.0, 0.0)


def _keepalive_loop():
    """后台 10Hz 重复发布最近一次指令, 保证取帧/计算耗时 >0.5s 时底盘不因指令超时停车。
    任何发布过的速度都会被保持; stop() 会置零, 因此停车兜底仍然有效。"""
    while True:
        try:
            with _keep_lock:
                vx, vy, wz = _last_pub["vx"], _last_pub["vy"], _last_pub["wz"]
            tw = Twist()
            tw.linear.x = max(-0.2, min(0.2, float(vx)))
            tw.linear.y = max(-0.2, min(0.2, float(vy)))
            tw.angular.z = max(-0.5, min(0.5, float(wz)))
            _cmd_pub.publish(tw)
        except Exception:
            pass
        time.sleep(0.1)


def get_pose():
    with _lock:
        return (_latest["x"], _latest["y"], _latest["yaw"])


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _norm_angle(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def _load_waypoints():
    try:
        with open(_WAYPOINTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[nav_control] 读取点位失败: {e}", flush=True)
        return {}


def rotate_to(target_yaw, timeout_s=NAV_TIMEOUT):
    """原地旋转到目标方位角, 角速度比例闭环。成功返回 True。"""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        _, _, yaw = get_pose()
        err = _norm_angle(target_yaw - yaw)
        if abs(err) < NAV_ANG_TOL:
            stop()
            return True
        # 小角度减速, 避免过冲
        wz = _clamp(err * 1.5, -NAV_ANG_MAX, NAV_ANG_MAX)
        if abs(err) < 0.15:
            wz = _clamp(err * 1.0, -NAV_ANG_MAX * 0.4, NAV_ANG_MAX * 0.4)
        publish_vel(0.0, 0.0, wz)
        time.sleep(1.0 / CTRL_HZ)
    stop()
    print(f"[nav_control] 转向超时 target={target_yaw:.2f} err={err:.3f}", flush=True)
    return False


def drive_straight(distance, timeout_s=NAV_TIMEOUT):
    """沿当前朝向直行 distance 米, 里程计位移闭环。成功返回 True。"""
    if distance <= NAV_DIST_TOL:
        return True
    x0, y0, _ = get_pose()
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        x, y, _ = get_pose()
        traveled = math.hypot(x - x0, y - y0)
        remain = distance - traveled
        if remain <= NAV_DIST_TOL:
            stop()
            return True
        vx = _clamp(remain * 0.8, 0.03, NAV_LIN_MAX)
        publish_vel(vx, 0.0, 0.0)
        time.sleep(1.0 / CTRL_HZ)
    stop()
    print(f"[nav_control] 直行超时 remain={remain:.3f}m", flush=True)
    return False


def navigate(waypoint):
    """真实导航: 读点位 -> 转向对准 -> 直行到位。返回 (success, info)。"""
    waypoints = _load_waypoints()
    wp = waypoints.get(waypoint)
    if wp is None:
        print(f"[nav_control] 点位不存在: {waypoint}", flush=True)
        return False, "unknown waypoint"
    tx, ty = float(wp["x"]), float(wp["y"])

    x, y, yaw = get_pose()
    dx, dy = tx - x, ty - y
    dist = math.hypot(dx, dy)
    print(f"[nav_control] 导航到 {waypoint} ({tx},{ty}) 当前 ({x:.2f},{y:.2f}) 距离 {dist:.2f}m", flush=True)

    # 已在目标范围内
    if dist <= NAV_DIST_TOL:
        stop()
        return True, f"already at {waypoint}"

    # 1) 转向对准目标方向
    target_yaw = math.atan2(dy, dx)
    if not rotate_to(target_yaw):
        return False, "rotate timeout"
    print(f"[nav_control] 已对准方向 {target_yaw:.2f} rad", flush=True)

    # 2) 直行到位 (里程计闭环)
    if not drive_straight(dist):
        return False, "drive timeout"
    print(f"[nav_control] 已到达 {waypoint}", flush=True)
    return True, "ok"


# ---- 启动 keepalive: 保证任意阶段 /cmd_vel 发布频率 >= 驱动超时阈值 ----
threading.Thread(target=_keepalive_loop, daemon=True, name="cmd-vel-keepalive").start()

for event in node:
    if event["type"] != "INPUT":
        continue
    eid = event["id"]

    # ---- 视觉伺服速度: 对齐阶段直接转发到底盘 ----
    if eid == "servo_vel":
        try:
            vel = json.loads(event["value"].to_pylist()[0])
            if vel.get("final"):
                stop()
                print("[nav_control] 伺服结束 停车", flush=True)
            elif vel.get("target_lost"):
                wz = float(vel.get("wz", 0.0))
                if abs(wz) > 0.01:
                    # 目标丢失但带角速度: 旋转搜索, 转发不停车
                    publish_vel(0.0, 0.0, wz)
                    print(f"[nav_control] 伺服搜索旋转 wz={wz:.2f}", flush=True)
                else:
                    stop()
                    print("[nav_control] 伺服停止 lost=True", flush=True)
            else:
                # 转发线速度+角速度 (支持视觉伺服平移 + 相机旋转扫描)
                publish_vel(vel.get("linear_x", 0.0), vel.get("linear_y", 0.0), vel.get("wz", 0.0))
        except Exception as e:
            print(f"[nav_control] servo_vel 解析失败: {e}", flush=True)
            stop()
        continue

    if eid != "nav_cmd":
        continue

    try:
        cmd = json.loads(event["value"].to_pylist()[0])
        waypoint = cmd["waypoint"]
        item = cmd["item"]
    except Exception as e:
        print(f"[nav_control] 无效 nav_cmd: {e}", flush=True)
        node.send_output("nav_done", pa.array([json.dumps(
            {"success": False, "waypoint": None, "item": None}, ensure_ascii=False)]))
        continue

    print(f"[nav_control] 收到导航指令: {waypoint} (取 {item})", flush=True)
    ok = False
    info = None
    try:
        ok, info = navigate(waypoint)
    except Exception as e:
        traceback.print_exc()
        ok, info = False, f"{type(e).__name__}: {e}"
    finally:
        stop()  # 任何出口都确保停车

    print(f"[nav_control] {'到达' if ok else '导航失败'}: {waypoint} ({info})", flush=True)
    node.send_output("nav_done", pa.array([json.dumps(
        {"success": ok, "waypoint": waypoint, "item": item}, ensure_ascii=False)]))
