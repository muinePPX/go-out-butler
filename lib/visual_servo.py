"""视觉伺服对齐控制律（纯逻辑库，可离线仿真 / 板端复用）

范式（官方 scene-template.yaml）:
  目标像素偏差 -> 相机反投影为横向偏移(米) -> 底盘横向速度(闭环)
  深度偏差      -> 前进/后退速度
  收敛(横向+深度均在容差内) 且 连续稳定 N 帧 -> 对齐完成

坐标系约定:
  相机: x 向右, y 向下, z 向前(深度)。像素偏差 -> x_m = (u-cx)*z/fx
  底盘: ROS REP-103, linear.x 向前, linear.y 向左
  LATERAL_SIGN: 相机安装方向/底盘朝向不一致时的符号修正(实车标定)

用法(离线仿真):
    python3 visual_servo.py
"""
import json
import math
import random


class VisualServoController:
    """单目标视觉伺服控制器。

    step(center_px, depth_m, frame_w) 每帧调用:
      - 帧间跳变过滤(max_target_jump_px)
      - 计算横向偏移 + 深度偏差
      - 输出底盘速度 {linear_x, linear_y}
      - 收敛且稳定 min_stable_frames 帧后 converged=True

    参数与官方 scene-template.yaml 对齐, 均可经 params dict 覆盖。
    """

    def __init__(self, fx, fy, cx, cy, params=None):
        self.fx = float(fx)
        self.fy = float(fy)
        self.cx = float(cx)
        self.cy = float(cy)

        p = params or {}
        self.lateral_gain = float(p.get("lateral_gain", 0.8))            # 横向偏差(米) -> 速度 比例
        self.lateral_speed_limit = float(p.get("lateral_speed_limit", 0.06))  # 最大横向速度 m/s
        self.forward_speed = float(p.get("forward_speed", 0.035))        # 前进速度 m/s
        self.backward_speed = float(p.get("backward_speed", -0.02))      # 后退速度 m/s(过冲回退)
        self.lateral_tolerance_m = float(p.get("lateral_tolerance_m", 0.018))     # 横向对齐容差(米)
        self.depth_tolerance_m = float(p.get("depth_tolerance_m", 0.02))         # 深度容差(米)
        self.grasp_depth_m = float(p.get("grasp_depth_m", 0.65))         # 对准收敛距离(米): 摄像头与目标停到 65cm
        self.min_stable_frames = int(p.get("min_stable_frames", 10))     # 稳定帧数门槛
        self.max_target_jump_px = float(p.get("max_target_jump_px", 80))  # 帧间中心跳变过滤
        self.lateral_sign = float(p.get("lateral_sign", 1.0))            # 横向速度方向修正
        self.depth_sign = float(p.get("depth_sign", 1.0))                # 深度方向修正
        self.lateral_deadzone_px = float(p.get("lateral_deadzone_px", 2.0))  # 像素死区,防抖

        self.reset()

    # ---- 状态 ----
    def reset(self):
        self.prev_dx_px = None
        self.stable_count = 0
        self.converged = False
        self.jump_rejects = 0
        self.last_info = None

    # ---- 每帧步进 ----
    def step(self, center_px, depth_m, frame_w=None):
        """center_px: [u, v]; depth_m: 目标深度(米); frame_w: 图像宽度(参考)。
        返回 (vel, info):
          vel : {"linear_x":.., "linear_y":..} 底盘速度
          info: {"dx_px","dx_m","dz_m","converged","target_lost"} 调试信息
        """
        u, v = center_px
        w = frame_w or (2.0 * self.cx)
        info = {"dx_px": None, "dx_m": None, "dz_m": None,
                "converged": False, "target_lost": False}
        self.last_info = info

        # 像素偏差(相对光轴/图像中心)
        dx_px = u - self.cx
        # 帧间跳变过滤: 中心突变视为误检, 保持上一帧速度(0)并继续
        if self.prev_dx_px is not None and abs(dx_px - self.prev_dx_px) > self.max_target_jump_px:
            self.jump_rejects += 1
            vel = {"linear_x": 0.0, "linear_y": 0.0}
            info.update({"converged": False})
            return vel, info
        self.prev_dx_px = dx_px

        # 深度
        depth_valid = depth_m is not None and depth_m > 0.0
        if not depth_valid:
            # 深度缺失: 目标可能太近/太远, 停住等下一帧
            vel = {"linear_x": 0.0, "linear_y": 0.0}
            info["target_lost"] = True
            return vel, info

        # 相机反投影 -> 横向偏移(米)
        dx_m = dx_px * depth_m / self.fx
        dz_m = depth_m - self.grasp_depth_m
        info["dx_px"] = dx_px
        info["dx_m"] = dx_m
        info["dz_m"] = dz_m

        # ---- 横向速度(闭环): 目标在右(dx_m>0) -> 向右移(linear_y<0, REP-103) ----
        if abs(dx_m) < self.lateral_tolerance_m:
            vy = 0.0
        else:
            vy = -self.lateral_sign * self.lateral_gain * dx_m
            vy = max(-self.lateral_speed_limit, min(self.lateral_speed_limit, vy))

        # ---- 深度速度: 太远前进, 太近后退 ----
        if dz_m > self.depth_tolerance_m:
            vx = self.forward_speed
        elif dz_m < -self.depth_tolerance_m:
            vx = self.backward_speed
        else:
            vx = 0.0

        vel = {"linear_x": vx, "linear_y": vy}

        # ---- 收敛判断: 横向+深度均达标, 连续稳定 min_stable_frames 帧 ----
        if abs(dx_m) <= self.lateral_tolerance_m and abs(dz_m) <= self.depth_tolerance_m:
            self.stable_count += 1
        else:
            self.stable_count = 0
        info["converged"] = self.stable_count >= self.min_stable_frames
        if info["converged"]:
            self.converged = True
            vel = {"linear_x": 0.0, "linear_y": 0.0}
        return vel, info

    # ---- 调试快照 ----
    def state_dict(self):
        return {
            "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
            "grasp_depth_m": self.grasp_depth_m,
            "lateral_tolerance_m": self.lateral_tolerance_m,
            "depth_tolerance_m": self.depth_tolerance_m,
            "min_stable_frames": self.min_stable_frames,
            "stable_count": self.stable_count,
            "converged": self.converged,
            "jump_rejects": self.jump_rejects,
            "last_info": self.last_info,
        }


# ==================== 离线仿真(自检) ====================
def simulate():
    """合成目标轨迹, 验证控制律能收敛。不依赖相机/底盘, 纯逻辑自检。"""
    fx, fy, cx, cy = 600.0, 600.0, 320.0, 240.0
    grasp_depth = 0.65
    ctrl = VisualServoController(fx, fy, cx, cy, {
        "grasp_depth_m": grasp_depth,
        "lateral_tolerance_m": 0.015,
        "depth_tolerance_m": 0.02,
        "min_stable_frames": 5,
    })

    # 模拟: 目标真实横向偏移 0.12m、深度 0.80m, 底盘以 servo 速度移动
    x_m, z_m = 0.12, 0.80          # 目标相对相机的空间位置(米)
    dt = 0.2
    frames = []
    for i in range(60):
        u = cx + x_m * fx / z_m    # 像素位置
        vel, info = ctrl.step([u, 120.0], z_m, 640)
        # 底盘运动更新(模拟): REP-103 linear_y<0 向右移(目标 x_m 减小), linear_x>0 前进(目标 z_m 减小)
        x_m += vel["linear_y"] * dt
        z_m -= vel["linear_x"] * dt
        frames.append((i, x_m, z_m, vel, info["converged"]))
        if info["converged"]:
            break
    print("=== 离线仿真 ===")
    print("目标起始 (x=%.3f m, z=%.3f m), 目标抓取深度 %.2f m" % (0.12, 0.80, grasp_depth))
    for f in frames:
        i, x, z, vel, conv = f
        print(" 帧%2d | 偏移x=%.4f z=%.3f | vx=%.3f vy=%.3f | %s" % (
            i, x, z, vel["linear_x"], vel["linear_y"],
            "ALIGNED" if conv else ""))
    ok = frames and frames[-1][4]
    print("结果: %s (帧数=%d)" % ("收敛 OK" if ok else "未收敛", len(frames)))
    return ok


if __name__ == "__main__":
    simulate()
