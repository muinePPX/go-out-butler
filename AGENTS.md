# AGENTS.md — 本项目的 Agent 工作规则

> 这些规则是所有代码助手在本仓库内工作时必须遵守的流程。
> 违反任一规则前先说明理由，否则按规则执行。

## 规则 1：动手前先检查当前设备/程序状态，能复用就不新连接

任何涉及板端（开发板）的操作，先做状态检查，**不要盲目 hdc tconn 或重启**：

1. 先探测连接状态：
   ```sh
   ping -n 2 10.45.162.231          # 网络是否通
   ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p 2223 root@10.45.162.231 "uptime"
   ```
   - 只有 `2223` 端口（mclaw sshd）是可用通道；`hdc 5555/8710`、`ssh 22` 均不通，不要浪费时间尝试。
2. 检查板端已运行的服务，确认是否真的需要重建/重连：
   ```sh
   docker ps -a --format '{{.Names}} {{.Status}}'          # rk3588s-vision 容器是否活着
   cd /data/local/robot && run dora list                   # dora 实例是否已在 Running
   ps -ef | grep -E 'orbbec|dora|camera_perception' | grep -v grep
   ls /dev/video*                                          # video20（机械臂摄像头）绑定是否还在
   ```
3. 如果服务已在正常运行（如主相机 29.8Hz、dora Running），**不要重建**，直接复用，只在必要时补充新连接。

## 规则 2：写代码/脚本前先查项目已有文件，不从头写

1. 先在项目里搜索是否已有可复用文件：
   - `tmp_*.sh` / `tmp_*.py`（本目录下已有大量验证过的诊断脚本，见《板端维护速查.md》第 5 节）
   - `nodes/`、`lib/`、`config/` 下的现有实现
   - 《板端维护速查.md》里记录的所有已验证命令、环境变量、坑
2. 已有脚本能满足需求时直接复用/微调；新建文件必须说明"为什么已有文件不可用"。
3. 改动 `nodes/`、`lib/` 等核心文件时，用 `replace_in_file` 做**最小改动**，禁止整文件重写。

## 规则 3：遇到问题优先查用户手册（robot_docs）

排障时先查官方文档，禁止凭经验乱试。手册位置与章节：

| 手册 | 路径 | 适用场景 |
|---|---|---|
| 安装 | `robot_docs-master-docs/docs/0-安装/` | HDC 安装使用、网络连接 |
| 开发板与工具 | `robot_docs-master-docs/docs/1-开发板和工具使用/` | shell 使用、自启服务、X11、WiFi |
| ROS 开发 | `robot_docs-master-docs/docs/2-ROS开发/` | ROS 节点/话题/tf |
| DORA 开发 | `robot_docs-master-docs/docs/3-DORA开发/` | 节点开发样例 |
| 调试 | `robot_docs-master-docs/docs/4-调试/` | 系统日志、崩溃日志、远程调试、性能、Dora 运行时、网络 |

排障顺序：**查速查手册（`板端维护速查.md`）→ 查 robot_docs 用户手册 → 查项目源码 → 再考虑 web 搜索**。

## 例外
- 用户明确指定要做某操作（如"重新绑定摄像头"）时，直接执行，但执行前后仍要检查状态并汇报。
