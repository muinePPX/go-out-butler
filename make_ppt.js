// 路演 PPT 生成脚本 - 出门管家机器人
// 运行: node make_ppt.js  -> 生成 出门管家机器人-路演.pptx
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3" x 7.5"
pres.author = "AIY Hackathon Team";
pres.title = "出门管家机器人";

// 配色方案：Ocean Gradient 科技深蓝
const C = {
  primary: "065A82",
  secondary: "1C7293",
  accent: "14B8A6",
  dark: "0F172A",
  body: "334155",
  muted: "64748B",
  light: "F8FAFC",
  card: "FFFFFF",
  white: "FFFFFF",
  accentSoft: "CCFBF1",
};
const FH = "Microsoft YaHei";
const FB = "Microsoft YaHei";

// shadow 工厂（避免复用对象被 mutate）
const mkShadow = () => ({ type: "outer", color: "000000", blur: 8, offset: 3, angle: 90, opacity: 0.12 });

// 内容页通用：左侧强调条 + 标题
function header(slide, title, subtitle) {
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.15, h: 7.5, fill: { color: C.accent } });
  slide.addText(title, { x: 0.6, y: 0.4, w: 11.5, h: 0.8, fontSize: 32, bold: true, fontFace: FH, color: C.primary, margin: 0 });
  if (subtitle) {
    slide.addText(subtitle, { x: 0.6, y: 1.15, w: 11.5, h: 0.4, fontSize: 16, fontFace: FB, color: C.muted, margin: 0 });
  }
}

// ===== 页1：标题页 =====
{
  const s = pres.addSlide();
  s.background = { color: C.primary };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 13.3, h: 0.12, fill: { color: C.accent } });
  s.addShape(pres.shapes.OVAL, { x: 9.5, y: 4.3, w: 4.5, h: 4.5, fill: { color: C.secondary, transparency: 65 } });
  s.addText("出门管家机器人", { x: 0.8, y: 2.2, w: 11, h: 1.3, fontSize: 50, bold: true, fontFace: FH, color: C.white, margin: 0 });
  s.addText("说一句话，备好出门行囊", { x: 0.8, y: 3.6, w: 11, h: 0.7, fontSize: 24, fontFace: FB, color: "B8E0E6", margin: 0 });
  s.addText("AIY Hackathon 2026  ·  深圳开鸿数字产业发展有限公司赛道", { x: 0.8, y: 6.0, w: 11, h: 0.5, fontSize: 15, fontFace: FB, color: "9CB8C4", margin: 0 });
}

// ===== 页2：痛点 =====
{
  const s = pres.addSlide();
  header(s, "出门，总在忘东西", "为谁而做 · 解决什么问题");
  const pains = [
    { t: "赶时间", d: "临出门才发现忘带钥匙、工卡，折返浪费时间" },
    { t: "靠记忆", d: "不同场景要带的东西不同，全靠脑子记，容易漏" },
    { t: "没帮手", d: "独居无人提醒，出门总不放心" },
  ];
  pains.forEach((p, i) => {
    const x = 0.8 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.2, w: 3.75, h: 3.3, fill: { color: C.card }, shadow: mkShadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.2, w: 3.75, h: 0.12, fill: { color: C.accent } });
    s.addText(p.t, { x: x + 0.3, y: 2.6, w: 3.15, h: 0.7, fontSize: 26, bold: true, fontFace: FH, color: C.primary, margin: 0 });
    s.addText(p.d, { x: x + 0.3, y: 3.6, w: 3.15, h: 1.5, fontSize: 16, fontFace: FB, color: C.body, margin: 0 });
  });
  s.addText("目标用户：每天通勤上班/上学、独居、常忘带物品的人", { x: 0.8, y: 6.1, w: 11.5, h: 0.5, fontSize: 15, italic: true, fontFace: FB, color: C.muted, margin: 0 });
}

// ===== 页3：解决方案 =====
{
  const s = pres.addSlide();
  header(s, "出门管家机器人", "用于什么场景 · 怎么解决");
  // 左侧概念说明
  s.addText([
    { text: "放置在门口的智能机器人", options: { bold: true, fontSize: 20, color: C.primary, breakLine: true } },
    { text: "\n", options: { fontSize: 8 } },
    { text: "出门前对它说一句话，例如「我要去运动」，机器人就会：", options: { fontSize: 16, color: C.body, breakLine: true } },
    { text: "\n", options: { fontSize: 6 } },
    { text: "理解你要去哪、做什么", options: { bullet: true, fontSize: 16, color: C.body, breakLine: true } },
    { text: "自动导航到物品存放点", options: { bullet: true, fontSize: 16, color: C.body, breakLine: true } },
    { text: "用相机识别物品，机械臂抓取", options: { bullet: true, fontSize: 16, color: C.body, breakLine: true } },
    { text: "把东西放进门口的包里", options: { bullet: true, fontSize: 16, color: C.body, breakLine: true } },
    { text: "语音告诉你「已备好水杯和毛巾」", options: { bullet: true, fontSize: 16, color: C.body } },
  ], { x: 0.8, y: 2.2, w: 6.0, h: 4.5, fontFace: FB, margin: 0, paraSpaceAfter: 6 });

  // 右侧场景示例卡片
  const scenes = [
    { t: "运动", items: "水杯 + 毛巾" },
    { t: "开会", items: "车钥匙 + 工卡" },
    { t: "上课", items: "课本 + 笔袋" },
  ];
  scenes.forEach((sc, i) => {
    const y = 2.2 + i * 1.5;
    s.addShape(pres.shapes.RECTANGLE, { x: 7.4, y, w: 5.0, h: 1.25, fill: { color: C.card }, shadow: mkShadow() });
    s.addShape(pres.shapes.RECTANGLE, { x: 7.4, y, w: 0.12, h: 1.25, fill: { color: C.accent } });
    s.addText(sc.t, { x: 7.8, y: y + 0.15, w: 1.8, h: 0.9, fontSize: 22, bold: true, fontFace: FH, color: C.primary, margin: 0, valign: "middle" });
    s.addText("→  " + sc.items, { x: 9.5, y: y + 0.15, w: 2.7, h: 0.9, fontSize: 18, fontFace: FB, color: C.body, margin: 0, valign: "middle" });
  });
}

// ===== 页4：系统架构 =====
{
  const s = pres.addSlide();
  header(s, "系统架构", "7 个 Dora 节点 · 数据流驱动");
  // 节点框工厂
  const box = (x, y, w, h, label, fill) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill }, shadow: mkShadow(), line: { color: C.secondary, width: 1 } });
    s.addText(label, { x, y, w, h, fontSize: 13, bold: true, fontFace: FB, color: C.white, align: "center", valign: "middle", margin: 0 });
  };
  const arrow = (x1, y1, x2, y2) => {
    s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: C.muted, width: 1.5 } });
  };
  // 流程节点
  box(0.5, 3.1, 1.7, 0.9, "语音输入", C.secondary);
  box(2.7, 3.1, 1.7, 0.9, "M-Claw\n决策", C.primary);
  box(4.9, 3.1, 1.9, 0.9, "任务调度\n(状态机)", C.primary);
  box(7.6, 1.9, 1.7, 0.8, "导航控制", C.secondary);
  box(7.6, 3.1, 1.7, 0.8, "相机感知", C.secondary);
  box(7.6, 4.3, 1.7, 0.8, "机械臂", C.secondary);
  box(9.9, 3.1, 1.7, 0.9, "反馈", C.accent);
  // 箭头
  arrow(2.2, 3.55, 2.7, 3.55);
  arrow(4.4, 3.55, 4.9, 3.55);
  arrow(6.8, 3.45, 7.6, 2.3);
  arrow(6.8, 3.55, 7.6, 3.5);
  arrow(6.8, 3.65, 7.6, 4.7);
  arrow(9.3, 2.3, 9.9, 3.45);
  arrow(9.3, 3.5, 9.9, 3.55);
  arrow(9.3, 4.7, 9.9, 3.65);
  // 用户
  s.addText("用户", { x: 11.9, y: 3.1, w: 1.2, h: 0.9, fontSize: 16, bold: true, fontFace: FB, color: C.primary, align: "center", valign: "middle", margin: 0 });
  arrow(11.6, 3.55, 11.9, 3.55);
  // 底部说明
  s.addText("基于 M-Robots OS 的 Dora 数据流框架，节点间通过 dataflow.yml 连接，数据以 Apache Arrow 零拷贝传递", {
    x: 0.8, y: 6.3, w: 11.5, h: 0.6, fontSize: 14, italic: true, fontFace: FB, color: C.muted, margin: 0, align: "center"
  });
}

// ===== 页5：M-Robots OS 能力结合 =====
{
  const s = pres.addSlide();
  header(s, "M-Robots OS 能力结合", "评分占比最高 25 分 · 必冲");
  // 左：M-Claw
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 2.1, w: 5.7, h: 4.3, fill: { color: C.card }, shadow: mkShadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 2.1, w: 5.7, h: 0.6, fill: { color: C.primary } });
  s.addText("M-Claw 智能体运行时", { x: 0.8, y: 2.1, w: 5.7, h: 0.6, fontSize: 20, bold: true, fontFace: FH, color: C.white, align: "center", valign: "middle", margin: 0 });
  s.addText([
    { text: "理解自然语言指令（「我要去运动」）", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "拆解为可执行步骤（导航→识别→抓取）", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "生成物品清单与执行策略", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "异常判断（物品未找到）并给出建议", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "反馈执行结果解释", options: { bullet: true, fontSize: 15, color: C.body } },
  ], { x: 1.1, y: 2.9, w: 5.1, h: 3.3, fontFace: FB, margin: 0, paraSpaceAfter: 8 });

  // 右：分布式软总线
  s.addShape(pres.shapes.RECTANGLE, { x: 6.8, y: 2.1, w: 5.7, h: 4.3, fill: { color: C.card }, shadow: mkShadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.8, y: 2.1, w: 5.7, h: 0.6, fill: { color: C.secondary } });
  s.addText("分布式软总线", { x: 6.8, y: 2.1, w: 5.7, h: 0.6, fontSize: 20, bold: true, fontFace: FH, color: C.white, align: "center", valign: "middle", margin: 0 });
  s.addText([
    { text: "开发板（决策大脑）", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "机器人本体（底盘+机械臂）", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "深度相机（感知端）", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "设备发现、状态同步、指令流转", options: { bullet: true, fontSize: 15, color: C.body, breakLine: true } },
    { text: "多终端协同形成统一任务系统", options: { bullet: true, fontSize: 15, color: C.body } },
  ], { x: 7.1, y: 2.9, w: 5.1, h: 3.3, fontFace: FB, margin: 0, paraSpaceAfter: 8 });
}

// ===== 页6：演示流程 =====
{
  const s = pres.addSlide();
  header(s, "现场演示流程", "输入 → AI处理 → 输出 完整闭环");
  const steps = [
    { n: "1", t: "语音输入", d: "用户说「我要去运动」" },
    { n: "2", t: "M-Claw 理解", d: "识别意图，生成物品清单" },
    { n: "3", t: "导航移动", d: "机器人驶向水杯存放点" },
    { n: "4", t: "相机识别", d: "深度相机确认水杯在位" },
    { n: "5", t: "机械臂抓取", d: "抓取水杯放入门口包中" },
    { n: "6", t: "语音反馈", d: "「已备好水杯和毛巾」" },
  ];
  steps.forEach((st, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.8 + col * 4.15;
    const y = 2.3 + row * 2.2;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 3.75, h: 1.8, fill: { color: C.card }, shadow: mkShadow() });
    // 序号圆
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.25, w: 0.7, h: 0.7, fill: { color: C.accent } });
    s.addText(st.n, { x: x + 0.2, y: y + 0.25, w: 0.7, h: 0.7, fontSize: 24, bold: true, fontFace: FH, color: C.white, align: "center", valign: "middle", margin: 0 });
    s.addText(st.t, { x: x + 1.05, y: y + 0.25, w: 2.5, h: 0.7, fontSize: 18, bold: true, fontFace: FH, color: C.primary, margin: 0, valign: "middle" });
    s.addText(st.d, { x: x + 0.3, y: y + 1.05, w: 3.15, h: 0.6, fontSize: 14, fontFace: FB, color: C.body, margin: 0 });
  });
}

// ===== 页7：技术亮点 =====
{
  const s = pres.addSlide();
  header(s, "技术亮点", "务实 · 可演示 · 可扩展");
  const points = [
    { t: "分层 MVP 设计", d: "Layer 0 全链路 mock 保底可演示 → Layer 1 逐个接入真实 API → Layer 2 软总线协同冲分。任何时刻都有可演示的东西。" },
    { t: "每个 API 都有降级方案", d: "M-Claw/软总线/ASR/相机/机械臂 API 均未知，每个都准备 fallback，确保部分不可用也能演示完整流程。" },
    { t: "状态机调度", d: "task_scheduler 节点维护「导航→识别→抓取」串行状态机，流程可控、易调试、单节点崩溃不影响全局。" },
    { t: "Dora 数据流热重载", d: "改 dataflow.yml 无需重启，现场快速迭代；一条命令启动全部 7 个节点。" },
  ];
  points.forEach((p, i) => {
    const y = 2.1 + i * 1.15;
    s.addShape(pres.shapes.OVAL, { x: 0.8, y: y + 0.1, w: 0.5, h: 0.5, fill: { color: C.accentSoft } });
    s.addShape(pres.shapes.OVAL, { x: 0.8, y: y + 0.1, w: 0.5, h: 0.5, fill: { color: C.accent, transparency: 30 } });
    s.addText(String(i + 1), { x: 0.8, y: y + 0.1, w: 0.5, h: 0.5, fontSize: 18, bold: true, fontFace: FH, color: C.primary, align: "center", valign: "middle", margin: 0 });
    s.addText(p.t, { x: 1.5, y: y, w: 4.0, h: 0.7, fontSize: 18, bold: true, fontFace: FH, color: C.primary, margin: 0, valign: "middle" });
    s.addText(p.d, { x: 5.6, y: y, w: 7.0, h: 0.95, fontSize: 14, fontFace: FB, color: C.body, margin: 0, valign: "middle" });
  });
}

// ===== 页8：总结 =====
{
  const s = pres.addSlide();
  s.background = { color: C.primary };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 7.38, w: 13.3, h: 0.12, fill: { color: C.accent } });
  s.addText("让机器人，做你的出门管家", { x: 0.8, y: 2.0, w: 11.5, h: 1.0, fontSize: 40, bold: true, fontFace: FH, color: C.white, margin: 0 });
  s.addText("一句话唤醒 · 自主导航 · 智能抓取 · 贴心反馈", { x: 0.8, y: 3.2, w: 11.5, h: 0.7, fontSize: 22, fontFace: FB, color: "B8E0E6", margin: 0 });
  // 三个价值点
  const vals = [
    { t: "场景价值", d: "解决日常忘带物品的真实痛点" },
    { t: "能力结合", d: "深度使用 M-Claw + 分布式软总线" },
    { t: "可扩展性", d: "场景配置化，轻松扩展更多出行场景" },
  ];
  vals.forEach((v, i) => {
    const x = 0.8 + i * 4.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 4.6, w: 3.75, h: 2.0, fill: { color: C.secondary, transparency: 55 } });
    s.addText(v.t, { x, y: 4.8, w: 3.75, h: 0.6, fontSize: 20, bold: true, fontFace: FH, color: C.white, align: "center", margin: 0 });
    s.addText(v.d, { x: x + 0.3, y: 5.5, w: 3.15, h: 0.9, fontSize: 14, fontFace: FB, color: "D6E8EC", align: "center", margin: 0 });
  });
  s.addText("AIY Hackathon 2026 · 出门管家机器人", { x: 0.8, y: 6.9, w: 11.5, h: 0.4, fontSize: 13, fontFace: FB, color: "9CB8C4", margin: 0 });
}

pres.writeFile({ fileName: "出门管家机器人-路演.pptx" }).then(() => {
  console.log("PPT 生成成功: 出门管家机器人-路演.pptx");
}).catch(e => {
  console.error("生成失败:", e.message);
});
