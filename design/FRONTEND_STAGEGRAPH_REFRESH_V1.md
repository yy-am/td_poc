# 前端改版方案 V1

更新时间：2026-03-31

适用范围：
- `frontend/src/views/ChatView.vue`
- `frontend/src/components/chat/MultiAgentBoardClean.vue`
- `frontend/src/components/chat/PlanFlowDeckClean.vue`
- `frontend/src/components/chat/AgentTimelineClean.vue`
- `frontend/src/components/chat/AgentDetailPanelClean.vue`

参考来源：
- `design/agent-visual-prototypes/v7-right-inspector-bilingual.html`
- 当前 `StageGraph v0` 与 `plan_graph` 事件结构

## 1. 当前问题

用户反馈成立，当前聊天页存在 4 个核心问题：

1. 整体风格过深、过硬。
- 现在的主界面仍然是深底、重边框、强分割的“控制台/运维台”风格。
- 对税务问数场景来说，这种气质会让页面显得压抑、冷硬、难亲近。

2. 中间主画布“像流程图，不像推理现场”。
- 当前 `PlanFlowDeckClean.vue` 虽然已经切成 `StageGraph v0`，但本质还是“线性阶段带 + 当前节点说明”。
- 用户能看到“现在到了第几步”，但看不出“模型此刻为什么在这一步、刚刚做了什么、下一步准备怎么走”。

3. 时间线和主图信息割裂。
- 左边时间线、右边节点图、下面 detail panel 各讲一部分事实。
- 这导致用户需要自己在 3 个区域来回拼信息，理解成本偏高。

4. 最终呈现更像工程调试台，而不是分析工作台。
- 我们现在是“把事件列出来”，但不是“把分析过程组织成一个人能顺着看懂的工作台”。
- 用户真正想看到的是：问题 -> 当前焦点 -> 已拿到的证据 -> 正在调用的工具 -> 下一步。

## 2. 改版目标

这版前端不追求“更炫”，而追求两件事：

1. 整体气质从“监控台”切换为“清新的分析工作台”。
2. 中间区域从“线性排布图”切换为“认知工作台”，让用户能看懂模型正在干什么。

明确约束：
- 保持浅色系。
- 不做深色 dashboard 风。
- 不继续使用 6 段横向线性阶段带作为主视觉。
- 不新增与当前后端协议不匹配的展示假象。
- 不用“花哨动画掩盖信息结构差”的方式处理问题。

## 3. 视觉方向

### 3.1 Visual Thesis

“像 Gemini 一样清新、轻透、留白充足，但中间工作区要更像一张动态分析桌，而不是普通聊天卡片流。”

### 3.2 色彩

基于参考 HTML 的浅色方向，建立新的 UI token：

- 页面底色：`#f6f9fd`
- 网格雾面层：`#eef4fb`
- 主面板：`rgba(255,255,255,.82)`
- 强面板：`rgba(255,255,255,.92)`
- 文本主色：`#152235`
- 次级文本：`#66788d`
- 主强调蓝：`#4f87ff`
- 辅助青：`#7fd7ff`
- 辅助薄荷绿：`#6dd8c2`
- 辅助琥珀：`#ffb764`
- 弱边框：`rgba(89,114,145,.12)`
- 柔和阴影：`0 18px 44px rgba(38,63,95,.08)`

### 3.3 字体

- 中文主字体：`"Segoe UI Variable Display", "Aptos", "Microsoft YaHei UI", sans-serif`
- 数据/代码字体：`Consolas, "JetBrains Mono", monospace`

### 3.4 氛围

- 保留轻微的网格纹理和雾面高光。
- 使用浅蓝、浅青、浅橙的低浓度径向光斑制造层次。
- 不再使用大面积纯黑、纯深蓝背景。

## 4. 信息架构

新页面结构从“左时间线 + 中图 + 下详情”改为“工作台三栏 + 底部输入”。

```text
┌─────────────────────────────────────────────────────────────┐
│ 顶部问题条：当前问题 / 当前阶段 / 当前焦点 / 运行状态          │
├───────────────┬──────────────────────────────┬──────────────┤
│ 左侧：会话与   │ 中央：认知工作台 Cognitive    │ 右侧：洞察检查  │
│ 过程缩略导航   │ Workbench                    │ Inspector      │
│               │                              │                │
│ - 会话列表      │ - 中心焦点卡                  │ - 当前节点详情   │
│ - 本轮事件摘要   │ - 周围证据卡 / 工具卡 / 阶段云  │ - semantic binding │
│ - 阶段迷你概览   │ - 底部近期事件带              │ - tool input/sql │
│               │ - 非线性 plan/stage 关系图      │ - 结果表/图/证据 │
├───────────────┴──────────────────────────────┴──────────────┤
│ 底部输入区：消息输入 / 快捷问题 / 发送状态                      │
└─────────────────────────────────────────────────────────────┘
```

## 5. 核心交互方案

## 5.1 顶部问题条：Question Ribbon

作用：
- 把“我问了什么”和“系统现在在做什么”固定在第一视线。

包含：
- 用户问题摘要
- 当前阶段中文名
- 当前活动节点标题
- 状态文案：`理解中 / 规划中 / 查询中 / 审查中 / 已完成 / 已中止`
- 当前模式标签：`StageGraph v0` 或 `真实执行计划`

不再使用：
- 大块欢迎语占住首屏
- 冗长的说明性 banner

## 5.2 中央区域：Cognitive Workbench

这是本次改版的核心。

### 为什么不能继续用线性排布

线性阶段带适合回答“系统处在第几步”，不适合回答：
- 这一步为什么发生
- 它用了什么工具
- 它拿到了什么证据
- 这一步和前后节点是什么关系

所以中间区域要从“阶段列表”改成“认知工作台”。

### 新的中心结构

中间工作台由 4 层组成：

1. 中心焦点卡 `Focus Card`
- 永远展示当前活动节点或当前选中节点
- 重点显示：
  - 节点标题
  - 当前行为
  - 一句话解释“为什么做这一步”
  - 当前工具
  - 当前输出摘要

2. 上游上下文带 `Why Lane`
- 放在焦点卡左上到左侧
- 展示：
  - 触发该节点的前序阶段/节点
  - 语义模型入口
  - 企业/期间等关键过滤条件

3. 下游预期带 `Next Lane`
- 放在焦点卡右上到右侧
- 展示：
  - 下一步可能进入的节点
  - 审查/报告等后续阶段

4. 底部事件胶片 `Recent Filmstrip`
- 只展示最近 5 到 8 条关键事件
- 按事件类型分组：`thinking / action / observation / review / answer`
- 点击任一事件，右侧 inspector 跳到对应详情

### 视觉形式

不是流程带，而是一块浅色雾面画布：
- 中心 1 张大焦点卡
- 周围 4 到 6 张卫星卡
- 节点之间用柔和弧线连接
- 当前活跃链路用高亮渐变线
- 已完成节点颜色轻微偏薄荷绿
- 正在运行节点偏浅琥珀
- 未来节点保持淡白/淡蓝

### 节点分三类显示

1. 阶段节点
- 表示 `intent / binding / planning / execution / review / report`
- 视觉更像“章节标签”

2. 执行节点
- 表示真实 `plan_graph` 里的 query / analysis / answer 节点
- 视觉更像“工作卡”

3. 证据节点
- 表示 observation、table result、chart result 的摘要
- 视觉更轻、更小，作为执行节点的挂件而不是主节点

## 5.3 左侧：Navigator

左侧不再叫“执行时间线”，而改成“导航侧栏”。

分为三块：

1. 会话列表
- 保留当前会话切换能力
- 视觉改浅色、弱边框、无深色底块

2. 本轮快照
- 当前阶段
- 当前节点
- 当前企业
- 当前期间
- 当前工具

3. 过程缩略视图
- 不是完整时间线
- 只保留关键里程碑：
  - 开始理解
  - 完成语义绑定
  - 生成计划
  - 执行关键查询
  - 审查
  - 生成回答

左侧的角色从“完整日志阅读器”改成“快速定位器”。

## 5.4 右侧：Inspector

右侧继续保留，但不再像工程控制台。

改造为 4 个信息块：

1. 当前焦点摘要
- 节点名
- 类型
- 状态
- 耗时

2. 语义上下文
- entry_model
- metrics
- dimensions
- entity filters
- time_context

3. 工具与证据
- 当前工具
- SQL/TDA-MQL 预览
- 表格结果
- 图表

4. 系统判断
- reasoning
- review verdict
- issues / suggestions

右侧要更像“分析说明板”，而不是“原始 JSON 容器”。

## 6. 与当前数据结构的映射

本方案不要求后端新增协议，先吃现有字段。

### 6.1 顶部问题条

来源：
- `ChatMessage.content`
- 最新 `stage_update.metadata.stage_id`
- 最新 `node_id`
- `is_final`

### 6.2 中心焦点卡

来源：
- 当前选中事件
- 或 `displayGraph.active_node_ids[0]`
- 结合最近一条 `thinking / action / observation`

### 6.3 卫星卡

来源：
- `plan_graph.nodes`
- `stage_graph.nodes`
- `depends_on`
- `tool_hints`
- `status`

### 6.4 底部事件胶片

来源：
- `steps.slice(-8)`

展示规则：
- `thinking` 显示“模型在想什么”
- `action` 显示“调用了什么”
- `observation` 显示“拿到了什么”
- `review` 显示“系统怎么看”

### 6.5 右侧 Inspector

来源：
- `metadata.semantic_binding`
- `metadata.tool_name / sql / sql_preview`
- `metadata.table_data`
- `metadata.chart_config`
- `metadata.reasoning`
- `metadata.review_points / issues / suggestions`

## 7. 组件改造建议

## 7.1 `ChatView.vue`

保留：
- 左会话管理
- 底部输入框

改造：
- 整页切换到浅色背景
- 引入顶部问题条
- 降低 welcome 区首屏占比

## 7.2 `MultiAgentBoardClean.vue`

当前问题：
- 结构仍是“上面 timeline + 中间图，下面 detail”

改造为：
- `QuestionRibbon`
- `AgentWorkbench`
- `InsightInspector`

建议拆分：
- `QuestionRibbon.vue`
- `WorkbenchCanvas.vue`
- `NavigatorRail.vue`
- `InsightInspector.vue`

## 7.3 `PlanFlowDeckClean.vue`

当前问题：
- 主视觉是横向阶段带

改造方向：
- 彻底替换为非线性工作台画布
- 允许 StageGraph 与真实 plan_graph 共用同一画布模型
- 中心聚焦当前节点，周围展示依赖和证据

建议新组件名：
- `WorkbenchCanvas.vue`

## 7.4 `AgentTimelineClean.vue`

当前问题：
- 太像日志流

改造方向：
- 从“完整时间线”改成“关键里程碑 + 最近事件胶片”
- 放到左导航和中间底部，而不是单独占一个主列

## 7.5 `AgentDetailPanelClean.vue`

当前问题：
- 深色
- 分块太像 debug 面板

改造方向：
- 改为浅色 inspector
- 强化排版层级
- 表格和 SQL 区域使用柔和浅灰底

## 8. 动效建议

只做 3 类轻动效：

1. 焦点切换时，中心卡片轻微放大并淡入
2. 活动链路高亮线缓慢流动
3. 最近事件胶片进入时做轻微上浮

不要做：
- 大范围飞线
- 大量节点抖动
- 卡片乱飘

## 9. 实施顺序

### Phase A：纯视觉重构

目标：
- 浅色化
- 替换深色背景、边框、阴影体系
- 先不改数据结构

范围：
- `ChatView.vue`
- `MultiAgentBoardClean.vue`
- `AgentDetailPanelClean.vue`

### Phase B：主画布重构

目标：
- 去掉线性阶段带
- 上线 `WorkbenchCanvas`

范围：
- 替换 `PlanFlowDeckClean.vue`
- 重组 `AgentTimelineClean.vue`

### Phase C：状态与证据联动

目标：
- 焦点卡、卫星卡、事件胶片、Inspector 四者联动
- 强化“模型正在干啥”的可读性

## 10. 这版设计的最终体验

用户进入页面后，应该在 3 秒内看懂：

1. 我当前问的是什么
2. 系统现在在做哪一步
3. 它用的是哪个语义模型/工具
4. 它刚刚拿到了什么结果
5. 下一步要去哪

一句话总结：

这次改版不是把颜色从黑改白，而是把页面从“日志型控制台”改成“可读的认知工作台”。

## 11. 已落地实现

截至 2026-03-31，本方案的 Phase A + Phase B 已经接入聊天页主入口：
- `ChatView.vue` 已切换为浅色工作台外壳
- 新组件链路：`MultiAgentBoardRefresh.vue -> NavigatorRail.vue + WorkbenchCanvas.vue + InsightInspector.vue`
- 中间区主视觉已从线性 stage ribbon 切换为非线性 Workbench
- 顶部 Question Ribbon 已接入真实问题文本、当前阶段、当前焦点、最新工具
- 当前实现不改后端协议，不增加任何未要求的 fallback 逻辑

## 12. 已验证
- `Set-Location frontend; npm run build` 通过
