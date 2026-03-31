# Agent Visual Prototypes

目录中的 [index.html](D:/lsy_projects/tda_tdp_poc/design/agent-visual-prototypes/index.html) 是一份可交互的执行计划可视化原型页。

## 目标

- 用“图”而不是“列表 + 底栏详情”来表达多阶段 Agent。
- 节点支持点击后查看更深信息。
- 真正思考过程默认收起，避免界面过载。
- 语义模型、tool、SQL、证据、审查结论都可以在节点级别展开。

## 三个方向

### V1 Command Graph / 指挥图谱板

- 特点：阶段轨道 + 中央图谱 + 右侧检查器。
- 优点：平衡、清晰、像正式产品。
- 最适合：当前主界面升级。

### V2 Stage Atlas / 阶段作战图

- 特点：阶段感最强，最容易让用户理解“各阶段在做啥”。
- 优点：适合流程治理、架构说明和 replan 展示。
- 最适合：领导汇报、实施方案说明。

### V3 Orbit Console / 轨道指挥舱

- 特点：最有“智能体围绕问题协作”的视觉感。
- 优点：炫酷、演示效果强。
- 最适合：Demo、展厅化展示、高层演示。

## 我当前的建议

如果目标是“既清晰又炫酷，而且能真落到现在前端代码里”，建议优先走：

1. 以 `V1` 作为正式产品主方案。
2. 吸收 `V2` 的阶段分区表达，用来强化 Understanding / Grounding / Planning / Execution / Review。
3. 只保留 `V3` 的部分视觉语言，比如中心问题锚点、发光激活态、轨道式高亮，而不要整页都做成轨道舱。

也就是：

`V1 结构 + V2 阶段表达 + V3 视觉气质`

## 参考案例

- [LangSmith Observability Quickstart](https://docs.langchain.com/langsmith/observability-quickstart)
- [LangGraph Studio](https://langchain-ai.github.io/langgraph/cloud/how-tos/studio/)
- [n8n Executions](https://docs.n8n.io/workflows/executions/)
- [CrewAI Flows](https://docs.crewai.com/concepts/flows)

## 当前前端对照

当前项目中和执行计划可视化直接相关的组件主要是：

- [MultiAgentBoardClean.vue](D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/MultiAgentBoardClean.vue)
- [PlanDAGViewClean.vue](D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/PlanDAGViewClean.vue)
- [AgentTimelineClean.vue](D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/AgentTimelineClean.vue)
- [AgentDetailPanelClean.vue](D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/AgentDetailPanelClean.vue)

这几版原型的核心，就是把上面 3 个区域从“并排信息块”升级成“图形化工作台”。
