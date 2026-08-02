---
name: butler-go-out
description: 出门管家。当用户说出出行场景（运动/开会/上课/通勤等）时，规划要带的物品清单，协调机器人导航到物品点位取物并拍照确认，最后反馈准备结果。可结合天气查询补充建议（下雨带伞、高温带水、天冷带外套）。
tags: [robot, butler, scenario, preparation, m-robots]
---

# 出门管家 (Butler Go Out)

根据用户出行场景，规划物品清单并协调机器人准备出门物品。

## 核心流程

1. 识别用户出行场景（运动/开会/上课/通勤等）
2. （可选）调用 `/weather` 查询当地天气，补充物品建议
   - 下雨 → 伞/防水袋
   - 高温 → 多带水
   - 天冷 → 外套
3. 调用 `prepare_items.py` 生成物品清单和对应点位
4. 对清单中每个物品，协调机器人执行：
   - 调用 `kaihong-robot-dog` Skill 导航到物品点位
   - 调用 `kaihong-robot-dog` 的 `photo` 或 `local-camera` 拍照确认物品
5. 汇总结果，反馈给用户（已准备好X、未找到Y）

## 调用方式

### 生成物品清单

```powershell
python "{{SKILL_DIR}}/scripts/prepare_items.py" <场景>
```

场景支持：运动、开会、上课

输出 JSON：

```json
{
  "scene": "运动",
  "items": [
    {"name": "水杯", "waypoint": "point_water", "qr_code": "QR_WATER"},
    {"name": "毛巾", "waypoint": "point_towel", "qr_code": "QR_TOWEL"}
  ],
  "total": 2
}
```

### 查看支持的场景

```powershell
python "{{SKILL_DIR}}/scripts/prepare_items.py" list
```

## 场景-物品对照

| 场景 | 物品 | 点位 |
|------|------|------|
| 运动 | 水杯、毛巾 | point_water, point_towel |
| 开会 | 车钥匙、工卡 | point_keys, point_badge |
| 上课 | 课本、笔袋 | point_book, point_pen |

现场需根据实际场地校准 `config/scenarios.json` 里的点位标识和二维码。

## 执行示例

用户说"我要去运动"时，M-Claw 应按以下步骤执行：

1. （可选）`/weather 查询深圳当前天气`，结合天气补充建议
2. 运行 `python "{{SKILL_DIR}}/scripts/prepare_items.py" 运动` 获取物品清单
3. 对清单中每个物品，调用 kaihong-robot-dog 导航并拍照：
   - `python kaihong-robot-dog/scripts/host/robotdog_client.py forward --meters <到水杯点位的距离>` 导航
   - `python kaihong-robot-dog/scripts/host/robotdog_client.py photo` 拍照确认
   - 重复直到所有物品点位都到达
4. 全部完成后反馈用户，例如："已为您准备好水杯和毛巾。今天32度，记得防晒。"

## 注意事项

1. 现场物品点位坐标需在 `config/scenarios.json` 中按实际场地校准
2. 机器人导航距离/角度需根据现场测试调整（用 kaihong-robot-dog 的 forward/turn-left）
3. 如果某物品未找到，继续准备其他物品，最后统一反馈
4. 涉及物理移动时，先确认机器人周围环境安全，避免碰撞
5. 若现场机器人非四足机器狗（如带机械臂的移动机器人），导航部分参考 kaihong-robot-dog 的 HTTP 控制模式，机械臂抓取需现场确认控制接口
