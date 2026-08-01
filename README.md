# 出门管家机器人

AIY Hackathon 2026 深圳站 - 深圳开鸿数字产业发展有限公司赛道参赛作品

## 场景

用户出门前对机器人说出出行场景（如"我要去运动"），机器人理解意图后，自动导航到各物品存放点位，用深度相机识别物品，机械臂抓取后放入门口的包中，并语音反馈准备结果。

## 架构

```
语音输入 -> M-Claw决策 -> 任务调度(状态机) -> 导航/识别/抓取 -> 反馈
```

7 个 Dora 节点，通过 `dataflow.yml` 连接，数据以 Apache Arrow 格式传递：

| 节点 | 职责 | Layer 0 (mock) | 现场替换 |
|------|------|----------------|----------|
| voice_input | 采集语音 | stdin 文字输入 | ASR 语音识别 |
| mclaw_decision | 意图理解+任务拆解 | scenarios.json 查表 | M-Claw API |
| task_scheduler | 状态机调度 | 同（逻辑不变） | 同 |
| nav_control | 底盘导航 | 打印日志+延时 | ROS cmd_vel |
| camera_perception | 物品识别 | 打印日志+延时 | 深度相机+二维码 |
| arm_control | 机械臂抓取 | 打印日志+延时 | ROS 关节控制 |
| feedback | 结果反馈 | print 文字 | TTS 语音播报 |

## 目录结构

```
出门管家机器人/
├── dataflow.yml          # Dora 数据流配置（7个节点连接关系）
├── nodes/                # 7 个 Python 节点
│   ├── voice_input.py
│   ├── mclaw_decision.py
│   ├── task_scheduler.py
│   ├── nav_control.py
│   ├── camera_perception.py
│   ├── arm_control.py
│   └── feedback.py
├── config/
│   ├── scenarios.json    # 场景-物品映射（运动/开会/上课）
│   └── waypoints.json    # 导航点位坐标
├── .vscode/launch.json   # debugpy 远程调试配置
└── README.md
```

## 运行方式（开发板）

```shell
# 1. 推送文件到开发板
hdc file send dataflow.yml /data/local/robot/
hdc file send nodes /data/local/robot/
hdc file send config /data/local/robot/

# 2. 启动 Dora
hdc shell
run dora up
run dora start /data/local/robot/dataflow.yml

# 3. 输入场景（在 voice_input 节点提示后输入）
运动

# 4. 停止
run dora list
run dora stop <dataflow-id>
```

## 降级策略

每个未知 API 都有 Layer 0 mock 实现。现场确认 API 后逐个替换，每个节点都标注了 `# 现场替换为:` 注释，方便定位替换点。即使部分 API 不可用，全链路 mock 仍可演示完整流程逻辑。
