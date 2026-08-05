"""开环往返测试: (0,0) -> (1,0) -> (0,0), 两点间距 1m

直接运行: python test_roundtrip_1m.py [--dry-run]
上车前: 1) 标定 LINEAR_SPEED / ANGULAR_SPEED  2) 替换 drive/turn 中的底盘指令

动作序列: 直行 1m -> 原地掉头 180° -> 直行 1m 返回
"""
import math
import sys
import time

# ---- 测试参数 ----
START = (0.0, 0.0)   # 起点
END   = (1.0, 0.0)   # 终点, 与起点相距 1m

LINEAR_SPEED  = 0.3   # 直行速度(米/秒), 现场标定: 走 1 米计时换算
ANGULAR_SPEED = 45.0  # 原地转向速度(度/秒), 现场标定: 转 180° 计时换算

DRY_RUN = "--dry-run" in sys.argv


def drive(distance):
    """开环直行: 时长 = 距离 / 速度, 结束后显式停车。"""
    duration = distance / LINEAR_SPEED
    print(f"[test] 直行 {distance:.2f}m (时长 {duration:.1f}s)", flush=True)
    if not DRY_RUN:
        # 现场替换为: 前进指令
        #   ROS:    twist.linear.x = LINEAR_SPEED, 持续 duration 后清零
        #   机器狗: os.system(f"python robotdog_client.py forward --meters {distance}")
        time.sleep(duration)
        # 现场替换为: 停车指令
    print("[test] 已停车", flush=True)


def turn(deg):
    """开环原地转向: 时长 = 角度 / 角速度。"""
    duration = abs(deg) / ANGULAR_SPEED
    print(f"[test] 原地转向 {deg:.1f}° (时长 {duration:.1f}s)", flush=True)
    if not DRY_RUN:
        # 现场替换为: 转向指令
        #   ROS:    twist.angular.z = ±math.radians(ANGULAR_SPEED), 持续 duration 后清零
        #   机器狗: os.system(f"python robotdog_client.py turn-left --degrees {abs(deg)}")
        time.sleep(duration)
        # 现场替换为: 停止转向指令


def main():
    distance = math.hypot(END[0] - START[0], END[1] - START[1])
    print(f"[test] 往返测试: {START} -> {END} -> {START}, 单程 {distance:.2f}m", flush=True)

    print("[test] --- 去程 ---", flush=True)
    drive(distance)   # (0,0) -> (1,0), 朝向 +x 直接直行

    turn(180.0)       # 原地掉头

    print("[test] --- 回程 ---", flush=True)
    drive(distance)   # (1,0) -> (0,0)

    print("[test] 往返完成, 已回到 (0,0)", flush=True)


if __name__ == "__main__":
    main()