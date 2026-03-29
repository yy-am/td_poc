# CLAUDE.md - 项目上下文与会话交接

## 文档定位
本文件给 Claude 类助手或其他新接手的 AI 使用，用来快速理解项目目标、恢复当前状态并继续推进实现。

## 项目目标
- 项目：TDA-TDP 语义化智能问数 Agent POC
- 目录：`D:\lsy_projects\tda_tdp_poc`
- 目标：完成一个可演示的问数系统，重点展示 Agent 推理过程、工具调用、数据对账与图表可视化。
- 业务主线：税务数据与财务数据自动对账，识别收入差异、税负异常与潜在风险。

## 截至 2026-03-29 的最新进展

### 运行链路
- **当前生效的聊天链路**：`backend/app/main.py → chat_v3.py → orchestrator.py`（Planner + Executor + Reviewer 三智能体协作）
- **旧链路**：`chat.py → react_agent_v4.py` 仍保留但不再被 main.py 注册
- 数据库：PostgreSQL 16
- 主后端地址：`http://127.0.0.1:8000`
- 前端地址：`http://127.0.0.1:5173`
- LLM：deepseek-v3.2（通过 OpenAI 协议统一客户端）

### 已经验证通过
- 后端健康检查：`/api/v1/health`
- 数据表清单：`/api/v1/datasource/tables`
- 会话接口：`/api/v1/sessions`
- 前端构建：`npm run build`
- 前端类型检查：`npx vue-tsc -b`
- 聊天 WebSocket：已能走通工具调用，中文问句可返回正确结果
- 数据初始化：已创建 28 张表，并灌入 Mock 数据
- 新聊天体验：先显示计划全景图，再执行工具；计划变化时会更新全景图
- 工具、SQL 和执行结果都已有中文语义说明
- 前端聊天界面已切到 ReAct 图谱视图：节点代表压缩后的真实步骤，点击节点可查看详情
- 已去掉“每步流式输出都自动滚动到底部”的行为，当前对话过程改为原地更新
- 最终图表和表格应固定展示在结果区，不要只放在节点详情里
- 最终回答区已支持富文本渲染，换行、列表、标题、引用和行内代码可正常展示
- 图谱节点标题已改为按上下文语义化命名，不再总是显示固定的泛化业务词
- 2026-03-29 晚间已核实 `/chat` 路由重新指向 `frontend/src/views/ChatView.vue`
- 2026-03-29 晚间已新增 clean 版聊天面板组件，并让 `ChatView.vue` 直接引用 clean 链路
- 对“发出问数需求但没看到 AI 计划”的排查结论是：前端实际加载的还是旧页面，不是后端没有产出 `plan` 事件

### 本轮真正完成的技术工作
- 将配置层和数据库层改造成兼容 SQLite 的本地运行模式
- 修复数据源接口的跨数据库兼容问题
- 修复 Mock 数据生成与清理逻辑在 SQLite 下的问题
- 修复初始化脚本的 Windows 编码和外键相关问题
- 新增健康检查接口
- 用新的 system prompt 与工具注册入口替换旧乱码链路
- 新增计划编排与语义解释层
- 新增新的前端执行面板组件，用于展示计划、执行、结果和中文解释
- 已将主后端 8000 切换到新版聊天链路
- 修复 `ReActGraphBoard.vue` 的历史乱码/半成品问题，组件已恢复为干净 UTF-8 版本
- 前端增加了按请求上下文推断“税务 / 账务 / 对账 / 风险 / 表结构 / 图表”的节点命名逻辑
- 后端语义命名层代码已补齐，`presentation.py` / `react_agent_v2.py` 现在会传递更明确的语义上下文字段

### 关键文件（多智能体架构）
- `backend/app/agent/orchestrator.py` — 三智能体调度器
- `backend/app/agent/planner_agent.py` — Planner 智能体
- `backend/app/agent/executor_agent.py` — Executor 智能体
- `backend/app/agent/reviewer_agent.py` — Reviewer 智能体
- `backend/app/agent/prompts/` — 三个 agent 的 system prompt
- `backend/app/api/chat_v3.py` — 新版 WebSocket endpoint
- `frontend/src/components/chat/MultiAgentBoard.vue` — 双视图容器
- `frontend/src/components/chat/AgentTimeline.vue` — 时间轴组件
- `frontend/src/components/chat/PlanDAGView.vue` — DAG 计划图
- `frontend/src/components/chat/AgentDetailPanel.vue` — 详情面板
- `frontend/src/views/ChatView.vue` — 主聊天页面
- `frontend/src/types/agent.ts` — AgentEvent 类型定义

## 现在不要误判的几点
- 项目不是”还没跑起来”，而是已经可以本地联调
- 当前默认数据库是 PostgreSQL 16，不是 SQLite
- 聊天架构已从单 agent ReAct 升级为 **三智能体协作**（Planner + Executor + Reviewer）
- 前端已从 ReActGraphBoard 切换为 **MultiAgentBoard** 双视图（时间轴 + DAG）
- 多智能体链路代码已写完、构建已通过，但端到端 WebSocket 测试尚未完成
- 历史文档中关于 Docker 未安装、SQLite 等内容已过期
- 仍有部分旧文件带乱码，但当前主链路已绕开，不影响继续开发

## 推荐恢复步骤
1. 阅读 `DESIGN.md`、`CODEX.md`、`CLAUDE.md`
2. 阅读 `.codex/skills/project-progress-handoff/SKILL.md`
3. 如用户显式提到 `$design-progress-sync`，按全局 skill 的流程执行
4. 用本地接口先核对真实状态：
```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/datasource/tables
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173
```
5. 如果服务未启动，再按 D 盘缓存方案启动，不要默认把缓存写回 C 盘

## 下一阶段建议
1. 先做多智能体端到端联调，确保 orchestrator 链路正常走通
2. 先在浏览器里实测一次 `/chat` 页面，确认发送问数问题后会先显示计划图，再出现执行和最终回答
3. 再补对话记录管理体验：会话重命名、删除、搜索
4. 继续语义模型：YAML 编辑、Agent 优先走 `semantic_query`
5. Phase 4：RAG / ChromaDB / 知识文档索引
6. 性能优化：Planner 首图延迟（换更快模型或缓存）

## 用户习惯
- 用户非常重视“项目方案和进展持续沉淀”
- 每次新对话开始时，都应该主动恢复项目方案、当前状态、下一步建议
- 每次有实质进展后，都应该更新 `CODEX.md` 和 `CLAUDE.md`
- 记录时要强调哪些是本轮已验证、哪些只是计划
- 尽量避免将可放在 D 盘的缓存、临时目录、运行产物放到 C 盘
- 用户非常重视体验：优先展示计划全景图，再执行；执行动作要带中文语义解释
- 用户不希望聊天过程像日志流一样不断向下堆叠并自动滚动；优先使用节点图、详情面板、原地更新
- 用户允许在合适时主动创建 subagent 并行处理独立子任务，以提升效率

## 技能
- 项目内 skill：`D:\lsy_projects\tda_tdp_poc\.codex\skills\project-progress-handoff`
- 全局 skill：`C:\Users\lsy\.codex\skills\design-progress-sync`
- 作用：固定“先恢复上下文，再写代码，关键方案变化回写设计文档，结束前回写交接”的工作习惯

## 额外说明
- 旧版乱码文档已备份为 `CLAUDE.legacy.md`
- 8003 / 8004 端口可能还留有临时联调实例，正式链路以 8000 为准
- 敏感配置不要写进本文件，统一以 `.env` 为准
## 2026-03-30 最新交接摘要

- 本轮重点问题是：用户发送复杂问数后长时间看不到反馈，且必须保证计划不是写死模板，而是真正 agentic。
- 已确认 jeniya 当前项目配置为 `https://jeniya.cn/v1`，并已通过脱离沙箱的真实探针请求验证连通成功。
- 根因分两层：
  - 体验层：之前用户要等到 Planner 首个结果出来才看到明显反馈
  - 执行层：复杂分析问句虽然能出计划，但 Executor 容易因为缺少真实 schema 上下文而写错 SQL

### 本轮核心改动

- 新增 `backend/app/agent/runtime_context.py`
  - 动态识别 query_mode
  - 解析企业候选和 taxpayer_id
  - 解析 `Q1-Q4` / 月份期间
  - 动态收集相关模型、事实表和字段 schema
- `backend/app/agent/orchestrator.py`
  - 在 Planner 前先发 `status` 事件
  - 这样用户发送消息后几乎立刻就能看到系统识别结果
- 新增 `backend/app/agent/planner_agent_v2.py`
  - Planner 基于 runtime_context 规划
  - 规划后会做一次 plan validation
  - 避免把复杂分析误判成 metadata 查询
- 新增 `backend/app/agent/executor_agent_v2.py`
  - Executor 拿到相关表真实字段 schema
  - 工具/SQL 出错后会自动根据报错做一次修正重试
- 新增 prompt：
  - `backend/app/agent/prompts/planner_prompt_v2.py`
  - `backend/app/agent/prompts/executor_prompt_v2.py`

### 当前已验证事实

- 简单问数 `当前系统里有多少张表？先给我计划，再回答。`
  - 约 `0.33s` 收到 `status`
  - 约 `14.03s` 收到真实 `plan`
  - 约 `36.81s` 收到最终回答
  - 结果正确：`28` 张表
- 复杂问数 `分析华兴科技2024年Q3增值税申报收入与会计账面的差异`
  - 约 `0.34s` 收到 `status`
  - 约 `28.08s` 收到真实 `plan`
  - 真实查询了：
    - `enterprise_info`
    - `recon_revenue_comparison`
    - `recon_adjustment_tracking`
  - Reviewer 对关键节点给出 `approve`
  - 最终答案已经能给出真实结论：
    - Q3 差异合计 `-539,338.77`
    - 主要为时间性差异

### 当前仍未完成

- 浏览器界面内的人工点击验证本轮未做，只做了后端 WebSocket 端到端验证。
- 图表节点在复杂分析路径中未强制触发验证。

### 对下一位助手的提醒

- 不要再怀疑 jeniya 是否连通；真实探针已成功。
- 不要再使用之前被 PowerShell 中文编码污染的测试方式；本项目做中文问句自动化验证时请优先用 Unicode 转义。
- 用户非常在意“计划不是写死的”，所以后续如果继续增强问数能力，优先增强 runtime_context、schema grounding、自动修正，而不是再加硬编码模板。
## 2026-03-30 最新补充

### 这一轮问题与结论
- 用户反馈：浏览器里发送问数后“还是没反应”
- 这次已确认不是后端 Planner 没产出，而是前端调用链路存在地址写死问题，导致浏览器可能卡在初始化或连接阶段

### 这一轮代码改动
- 前端
- `frontend/src/stores/chat.ts` 改为使用运行时 `getApiBase()`
- `frontend/src/composables/useWebSocket.ts` 改为使用运行时 `getWebSocketBase()`
- `frontend/src/views/ChatView.vue` 增加 `initError` 展示
- `frontend/src/views/DashboardView.vue`
- `frontend/src/views/SemanticView.vue`
- `frontend/src/views/SemanticView_v2.vue`
- `frontend/src/views/SettingsView.vue`
- 上述页面都已去掉写死的 `localhost:8000`
- 后端
- 新增 `backend/app/agent/prompts/reviewer_prompt_v2.py`
- 新增 `backend/app/agent/reviewer_agent_v2.py`
- `backend/app/agent/orchestrator.py` 切换到 Reviewer v2

### 本轮真实验证
- `npm run build` 已通过
- `http://127.0.0.1:5173/api/v1/sessions` 和 `http://localhost:5173/api/v1/sessions` 都返回 `200`
- 通过 `5173` 代理层真实建立了 WebSocket，会收到 `plan` 事件
- 简单问题验证通过：约 10.95 秒收到 `plan`，最终回答 28 张表
- 复杂问题验证通过：约 26.77 秒收到 `plan`，中途发生一次 `replan`，约 128.59 秒收到最终完整报告；Q3 累计差异 `-540,338.77` 元，主要为时间性差异

### 现在不要再误判的点
- “没反应”当前最主要不是 jeniya 不通，也不是后端没有计划，而是前端地址写死导致浏览器没有走通整条链
- 当前 `/chat` 已在 `5173 -> /api,/ws 代理 -> 8000` 这条真实路径上跑通
- 如果用户浏览器还看不到更新，优先考虑页面没有刷新，而不是再次怀疑后端没产出计划

### 下一步
1. 若用户仍说页面无反馈，先看浏览器控制台和 Network
2. 重点看 `/api/v1/sessions`、`/api/v1/sessions/{id}/messages`、`/ws/chat/{id}`
3. 若继续优化体验，优先缩短首个 `plan` 的等待时间
