# CLAUDE.md - 项目上下文与会话交接

## 2026-03-31 Agent Flow / Validation Update

- 新增根目录文档：`AGENT_FLOW_CURRENT.md`
  - 可直接查看当前真实阶段、调用时序、大模型调用次数和改进建议
- 本轮已落地两个关键改进：
  - `TDA-MQL` 草拟阶段正式校验，失败会阻断在 `tda_mql_draft`
  - 审查 / 汇总阶段不再默认通过或自动拼 fallback answer
- 本轮新增或更新测试：
  - `backend/tests/agent/test_reviewer_agent_v2.py`
  - `backend/tests/agent/test_orchestrator.py`
  - `backend/tests/agent/test_stage_graph_v1_lite_spec.py`
- 当前最新后端回归结果：`57 passed, 1 warning`
- 后续第三个改进点仍待实现：审查成本优化，建议走“规则先审，模型补审”

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
- **旧链路状态**：历史 `chat.py / react_agent* / 非 clean 前端组件` 已于 2026-03-30 清理出仓库，不再保留重复实现
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

## 2026-03-30 文档补充

- 本轮新增 `PROJECT_CODE_GUIDE.md`，用于系统化介绍当前项目结构、代码包职责、主运行流程与阅读顺序。
- 该文档基于 `DESIGN.md`、`CODEX.md`、`CLAUDE.md` 与当前实际源码整理，明确区分了：
  - 当前生效链路
  - 历史/兼容文件
  - 尚未落地的占位目录
- 本轮没有修改运行逻辑，属于文档沉淀工作，便于后续快速理解系统设计与代码边界。

## 2026-03-30 Phase 1（TDA-MQL）新增进展

### 新文档
- `design/DESIGN_V2_MQL_STAGEGRAPH.md`
- `design/PHASE1_TDA_MQL.md`
- `DESIGN.md` 已加入 v2 入口说明

### 新能力
- 新增 `backend/app/semantic/mql.py`
  - 提供 `TDA-MQL` 编译与执行入口
  - 目前是语义底座能力，不在 orchestrator 主链里
- `backend/app/api/semantic_v2.py`
  - 新增 `POST /api/v1/semantic/mql/validate`
  - 新增 `POST /api/v1/semantic/mql/query`
- `backend/app/mcp/tools/registry_v2.py`
  - 新增 `mql_query` tool
- `backend/app/agent/executor_agent_v2.py`
  - 已支持在显式 `tda_mql` 绑定时优先执行 `mql_query`
  - 显式 `tda_mql` 不允许隐藏 fallback 到 `sql_executor`
- 语义资产目录已扩展输出：
  - `relationship_graph`
  - `metric_lineage`
  - `detail_fields`
  - `materialization_policy`
  - `query_hints`

### 新增税务对账语义资产
- `mart_revenue_timing_gap`
- `mart_vat_payable_snapshot`
- `mart_cit_adjustment_bridge`
- 当前语义资产总数：`25`

### 已验证
- `tests/semantic/test_tda_mql.py` 通过
- `tests/agent/test_executor_agent_v2.py` 通过
- `tests/agent/test_runtime_context.py` 通过
- `tests/agent/test_semantic_grounding.py` 通过
- 合计 `20` 个测试通过

### 尚未开始
- Planner 稳定产出 `mql_query` 计划节点
- StageGraph 改造
- 人工审核断点
- compare / attribution / Python 分析执行链

### 接手提醒
- 这轮用户特别强调：**不要写没让你做的 fallback 逻辑**
- 当前 Phase 1 对不支持的 MQL 能力采用“显式报错”，不是偷偷回退到 SQL

## 2026-03-30 冗余文件清理补充

### 本轮完成
- 清理主链路之外的历史源码：
  - 后端 API：`chat.py`、`chat_v2.py`、`chat_ws.py`、`router.py`、`semantic.py`、`mock_data.py`
  - 后端 Agent：第一代三智能体、`react_agent*`、旧 `system_prompt*`、旧 prompt 文件、旧 `registry.py`、旧 `semantic/service.py`
  - 前端：`ChatView_v2.vue`、`SemanticView.vue`、非 clean 聊天组件
- 清理本地运行残留：多数历史日志、测试 SQLite、legacy 交接文档、`backend/app/**/__pycache__`
- 更新 `PROJECT_CODE_GUIDE.md`，把旧的“历史文件仍保留”描述改成当前真实仓库状态

### 本轮已验证
- 当前真实主链路仍是：
  - 后端：`main.py -> router_v2.py / chat_v3.py -> orchestrator.py`
  - 前端：`ChatView.vue -> useWebSocket.ts -> MultiAgentBoardClean.vue`
- 当前 `.env` 指向 PostgreSQL；被删除的 `.db` 文件属于本地测试/调试残留，不是现行数据库
- `frontend` 目录下重新执行 `npm run build` 成功
- 用新的 Python 进程重新导入 `app.main`、`router_v2`、`chat_v3`、`orchestrator` 与 `*_agent_v2` 成功
- 本地 `GET /api/v1/health` 与 `GET /api/v1/datasource/tables` 均返回 `200`

### 尚未处理完
- `backend-server-8000.log` 与 `frontend-server.log` 正被运行中的进程占用，暂未删除；不影响本轮代码清理

## 2026-03-30 语义层升级补充（本轮）

### 本轮完成
- 语义层已从“少量 YAML 模型 + 旧 `semantic_binding.models`”升级为“分层语义资产 + semantic-first 执行”。
- 新增主语义资产目录文件：`backend/app/mock/semantic_assets.py`，并将 seed 入口统一到 `semantic_seed.py`。
- 新增 `compiler_v2.py / service_v3.py / catalog.py`，支持：
  - 多源 `sources + joins`
  - 表达式指标/维度
  - 实体 resolver
  - `entity_filters / resolved_filters / grain`
- Agent 契约升级：
  - `understanding_result` 新增 `semantic_scope` 与 `resolution_requirements`
  - `semantic_binding` 新增 `entry_model / supporting_models / entity_filters / resolved_filters / fallback_policy`
  - Executor 已实现 semantic-first 直接执行，失败时再做 repair / fallback。
- 前端已同步到新契约：语义管理页按三层分类展示，聊天详情面板可直接显示语义绑定与解析过滤条件。

### 本轮验证事实
- 后端 `app.main` 导入成功。
- PostgreSQL 仍正常，`/api/v1/health` 返回 `ok`。
- 语义资产 seed 已成功写库，`sys_semantic_model` 当前总数 42；其中新增 22 条活动模型，旧模型归档保留。
- 函数级验证：
  - `mart_tax_risk_alert` 能通过 `enterprise_name -> taxpayer_id` 解析查询到 `鑫隆商贸有限公司` 风险预警。
  - `mart_revenue_reconciliation` 能查询 `华兴科技有限公司` 2024Q3 三个月税会收入差异。
- API 级验证：`/api/v1/semantic/query` 已返回 `resolved_filters` 与 `resolution_log`。
- 前端 `npm run build` 通过。

### 仍需注意
- 当前常驻在 8000 的旧进程没有在本轮重启；如果要看浏览器真实 UI，需要先重启到本轮代码。
- 本轮没有依赖外部 LLM 服务做真实聊天回放，因此“Semantic-first 聊天链路”属于代码已完成、函数/API 已验证、浏览器端待重启后联调。
- `ExecutionAtlasPrototypeView.vue` 是未并入主链的原型文件，本轮通过 `tsconfig.app.json` 排除，避免阻塞主应用构建；不要误把它当成主链页面。

### 下次最优先动作
1. 重启后端到当前代码版本。
2. 浏览器联调 `/chat` 与 `/semantic`。
3. 用风险预警、收入对账两个问题做真实 UI 回归。
4. 如果还有问题，先查 `semantic_binding` 和 `resolved_filters` 是否正确透出，再查执行层。

## 2026-03-30 Phase 1 继续推进补充

### 本轮完成
- Planner 显式 MQL 绑定补强：
  - `backend/app/agent/planner_agent_v2.py` 现在会在命中 `recommended_tool=mql_query` 的复合语义资产时，主动补齐
    - `tool_hints=["mql_query"]`
    - `semantic_binding.query_language="tda_mql"`
    - `time_context`
  - 同时避免默认把模型全部 metrics / dimensions 塞进 binding，优先保留用户问题里显式提到的字段
- `backend/app/agent/prompts/planner_prompt_v3.py`
  - 已同步要求 Planner 在语义层推荐 MQL 时直接产出 MQL 路径
- `backend/app/agent/understanding_agent.py`
  - 修复 fallback 场景下候选模型为空的兼容问题
- 新增税务对账语义资产：
  - `mart_cit_settlement_bridge`
  - `mart_vat_declaration_diagnostics`
  - `mart_depreciation_timing_difference`
  - 当前语义资产总数已到 `28`
- 新增/更新测试：
  - `backend/tests/agent/test_planner_agent_v2.py`
  - `backend/tests/semantic/test_tda_mql.py`
- 文档已同步更新：
  - `design/PHASE1_TDA_MQL.md`
  - `design/DESIGN_V2_MQL_STAGEGRAPH.md`

### 本轮验证事实
- `Set-Location backend; .\.venv\Scripts\python.exe -m pytest`
  - 共 `28` 个测试通过
- 已确认新增 3 个语义资产能被 `SEMANTIC_MODEL_RECORDS` 正常加载

### 仍未完成
- 还没有用真实 LLM 主链观察 Planner 是否稳定每次都先产出 `mql_query` 计划节点
- 还没有开始 StageGraph v0
- compare / attribution / Python analysis 仍未实现

### 接手提醒
- 用户本轮再次强调：**不要写没让你做的兜底逻辑**
- 当前 Phase 1 仍坚持：
  - 未支持能力明确报错
  - 不做隐式 SQL fallback
- 下一步优先做真实问句回归 Planner/Executor 主链，再决定是否进入 StageGraph 实现

## 2026-03-30 StageGraph v0 与真实回归补充

### 本轮完成
- `backend/app/llm/client.py`
  - 新增仅针对 `APIConnectionError / APITimeoutError` 的瞬时重试
  - 没有新增任何语义 fallback 或 SQL fallback
- 在真实 LLM 回归后，继续补强了税务对账语义检索：
  - `backend/app/agent/semantic_grounding.py`
  - `backend/app/agent/runtime_context.py`
  - `backend/app/mock/semantic_assets.py`
  - 新增/补强 `汇算清缴桥接`、`增值税申报诊断` 等 alias 与领域词
- `StageGraph v0` 已经落地：
  - 新增 `backend/app/agent/stage_graph.py`
  - `backend/app/agent/orchestrator.py` 已显式发出 `stage_update`
  - `frontend/src/types/agent.ts`
  - `frontend/src/components/chat/MultiAgentBoardClean.vue`
  - `frontend/src/components/chat/AgentTimelineClean.vue`
  - `frontend/src/components/chat/AgentDetailPanelClean.vue`
  - 前端已支持阶段图与阶段事件展示
- 新增测试：
  - `backend/tests/llm/test_client.py`
  - `backend/tests/agent/test_stage_graph.py`
  - `backend/tests/agent/test_orchestrator.py`

### 本轮验证事实
- 真实 LLM 回归（改进后）：
  - `backend-live-planner-regression-escalated-v2.json`
  - 统计结果：`total_runs=6, llm_plan_runs=5, fallback_runs=1, mql_path_runs=5`
  - 收入差异问句：`2/2` 命中 `mql_query`
  - VAT 申报诊断：`2/2` 命中 `mql_query`
  - CIT 汇缴桥接：`1/2` 命中 `mql_query`
  - 剩余 1 次 miss 已定位为外部 `APIConnectionError`，不是语义路由偏差
- `Set-Location backend; .\.venv\Scripts\python.exe -m pytest`
  - 共 `37` 个测试通过，`1` 个既有 Pydantic warning
- `Set-Location frontend; npm run build`
  - 已通过
  - 首次在沙箱内因环境级 `spawn EPERM` 失败
  - 提权重跑后通过，因此不是业务代码错误

### 当前最可信结论
- 真实问句下，只要成功拿到 LLM 计划，Planner 已基本稳定走 MQL 主路径
- `StageGraph v0` 已经进入主链路，且前端可见
- 仍然没有加入用户未要求的隐藏兜底逻辑

### 仍未完成
- 还没有做浏览器真实 WebSocket 回归，确认 UI 中先显示 `StageGraph v0`、后显示真实 LLM `plan_graph`
- 还没有进入 `StageGraph v1` 的人工审核断点、暂停/恢复、阶段持久化

### 接手最优先动作
1. 先看 `design/DESIGN_V2_MQL_STAGEGRAPH.md`
2. 再看 `backend/app/agent/stage_graph.py` 与 `backend/app/agent/orchestrator.py`
3. 用浏览器真实走一遍 `/chat`，确认阶段图与计划图切换正常

## 2026-03-30 前端 StageGraph 视图对齐
### 本轮完成
- `frontend/src/components/chat/MultiAgentBoardClean.vue`
  - 已把中间图切换到 `PlanFlowDeckClean.vue`
- `frontend/src/components/chat/PlanFlowDeckClean.vue`
  - 现在是前端主链路的中间图组件
  - 在真实 `plan_graph` 出来前，优先展示 `StageGraph v0`
  - 保留真实 LLM `plan_graph` 的展示能力
- `design/agent-visual-prototypes/v7-right-inspector-bilingual.html`
  - 已按当前 6 段阶段流更新关键视觉语义

### 本轮验证事实
- `Set-Location frontend; npm run build` 已通过
- 本轮只涉及展示层和设计参考，不涉及执行逻辑改动
- 没有新增任何隐藏 fallback 或隐式 SQL 降级

### 下次最优先动作
1. 浏览器真实联调 `/chat`
2. 确认用户先看到 `StageGraph v0`，后看到真实 `plan_graph`
3. 然后进入 `StageGraph v1` 的人工审核断点

## 2026-03-31 服务重启与真实联调
### 本轮已完成
- 已重新启动前端与后端常驻服务：
  - 前端 `http://127.0.0.1:5173`
  - 聊天页 `http://127.0.0.1:5173/chat`
  - 后端 `http://127.0.0.1:8000`
- 修复 `PlannerAgent` 的 prompt 载荷构造：
  - 新增 `_compact_understanding_result`
  - 新增 `_compact_runtime_context_for_prompt`
  - 新增 `_build_prompt_payload`
  - 将 `planning_seed` 显式加入 Planner / Replan 输入
- 新增测试 `test_build_prompt_payload_compacts_runtime_context_and_understanding`
- 后端测试通过：`Set-Location backend; .\.venv\Scripts\python.exe -m pytest tests/agent/test_planner_agent_v2.py tests/agent/test_orchestrator.py -q`

### 本轮真实验证
- `GET http://127.0.0.1:8000/api/v1/health` 返回 PostgreSQL 正常
- `GET http://127.0.0.1:5173` 返回 `200`
- `GET http://127.0.0.1:5173/chat` 返回 `200`
- 真实 WebSocket 回归（走 `5173 -> /ws -> 8000` 代理）已确认：
  - 收到 `StageGraph v0` 阶段事件
  - Planner 已成功生成真实计划，不再停在 `Planner 未能生成真实 LLM 计划`
  - 执行链已进入 `Resolve Enterprise Identity` 与 `Query Revenue Reconciliation`
  - `Query Revenue Reconciliation` 已命中 `mql_query`

### 关键结论
- 当前服务已经可以打开并看到最新一版 StageGraph 主链路效果
- 本轮没有加入任何隐藏 fallback / 隐式 SQL 降级
- 人工审核断点仍未开始做，符合当前用户要求

## 2026-03-31 前端清新化改版方案
### 本轮完成
- 新增前端设计文档：`design/FRONTEND_STAGEGRAPH_REFRESH_V1.md`
- 设计结论已明确：
  - 整体风格从深色控制台切换为浅色、轻透、Gemini 风格分析工作台
  - 中间主图不再使用线性阶段带作为主视觉
  - 新方案改为 `Question Ribbon + Cognitive Workbench + Insight Inspector`
  - 中间区域要突出“模型此刻在干什么”，而不是仅展示“第几步”

### 当前状态
- 这轮只完成设计方案，尚未开始前端重构代码

## 2026-03-31 前端工作台换代已接入
### 本轮完成
- 聊天页入口已切到 `frontend/src/components/chat/MultiAgentBoardRefresh.vue`
- 新增 `NavigatorRail.vue / WorkbenchCanvas.vue / InsightInspector.vue`
- `ChatView.vue` 已完成浅色化，包含会话侧栏、欢迎区、输入区和消息容器
- 中间主图已切为非线性工作台，不再以线性 stage ribbon 作为主视觉
- 没有新增任何隐藏 fallback / SQL 自动降级 / 伪造状态

### 验证
- 前端构建通过：`Set-Location frontend; npm run build`

## 2026-03-31 P0/P1 close-out

### This round delivered
- P0:
  - single-turn planner -> `mql_query` main path kept stable under test
  - no hidden fallback was added
- P1:
  - `TDA-MQL` compare support landed for `yoy / mom / qoq / previous_period`
  - drill-down stays explicit and asset-driven via `detail_fields`
  - runtime stage flow upgraded to `StageGraph v1-lite`
  - frontend workbench can consume the richer stage model plus compare/drilldown metadata

### Self-test status
- Targeted backend tests passed:
  - `backend/tests/semantic/test_tda_mql.py`
  - `backend/tests/agent/test_stage_graph.py`
  - `backend/tests/agent/test_stage_graph_v1_lite_spec.py`
  - `backend/tests/agent/test_orchestrator.py`
- Full backend suite passed:
  - `43 passed, 1 warning`
- Frontend build passed:
  - first sandbox build hit `spawn EPERM`
  - rerun outside sandbox passed

### Important guardrails
- Keep explicit failure for unsupported capabilities
- Do not add hidden fallback or implicit SQL downgrade
- Human gate and multi-turn remain deferred by user request

### Cleanup note
- Obsolete temporary `.new` files have been deleted.
- The old unused chat workbench files replaced by the refresh workbench have been removed.

## 2026-03-31 出口退税对账设计补充

### 本轮完成
- 新增 `design/EXPORT_REBATE_RECONCILIATION_V1.md`
- 这份文档把“出口退税账面收入与税基金额对账”重构成更接近企业真实场景的语义资产设计，而不是继续停留在月度结果表
- 设计明确了三张核心事实表：
  - `fact_export_book_revenue_line`
  - `fact_export_refund_tax_basis_line`
  - `fact_export_contract_discount_line`
- 其中第三张折扣事实表是关键新增，用来结构化记录合同折扣、折让、返利及其对账面 / 税基的影响
- 已同步把入口写回：
  - `design/DESIGN_V2_MQL_STAGEGRAPH.md`
  - `design/PHASE1_TDA_MQL.md`
  - `design/PROJECT_PROGRESS_V2.md`

### 本轮没有做的事
- 没有实现新的 SQLAlchemy 模型
- 没有修改 mock 数据生成
- 没有把新资产接入 `semantic_assets.py`
- 没有运行 pytest / build

### 接手时不要误判
- 这轮是“设计已定”，不是“代码已完成”
- 现有 `mart_revenue_reconciliation` 仍是运行中资产，但它不应被误认为出口退税场景的最终企业级设计
- 后续实现时，应优先从三张事实表和折扣桥接开始，不要再先做新的月度结果表

### 最优先恢复动作
1. 阅读 `design/EXPORT_REBATE_RECONCILIATION_V1.md`
2. 再读 `design/DESIGN_V2_MQL_STAGEGRAPH.md`
3. 若要落地实现，顺序优先：
   - ORM
   - mock generator
   - semantic assets
   - regression tests

## 2026-03-31 出口退税场景实现更新
### 已完成
- 设计已转为代码：
  - 3 张底层事实表
  - mock 单证链数据
  - 5 个相关语义资产
  - `TDA-MQL time_context.role` 支持多时间角色过滤
- 明确遵守用户约束：不把这个场景写死成离线分析文件，而是保留前端提问后由现有 agent 链路动态完成分析

### 已验证
- `backend/tests/semantic/test_tda_mql.py`
- `backend/tests/agent/test_semantic_grounding.py`
- `backend/tests/agent/test_executor_agent_v2.py`
- `backend/tests/agent/test_runtime_context.py`
- 结果：`28 passed, 1 warning` + `7 passed`

## 2026-03-31 出口退税语义入口修正
### 已完成
- 根据用户反馈修正语义入口：
  - 首跳做出口退税对账
  - 二跳查差异合同下的折扣记录
  - 三跳才进入折扣传递支持分析
- 已把 `mart_export_discount_bridge` 设为 `entry_enabled=false`
- 已在 grounding 打分里加入非入口主题降权，避免普通对账问句首跳命中折扣支持主题
- 已扩充 `fact_export_contract_discount_line` 的真实问法别名，支持“合同有没有折扣/是否有折扣单/折扣记录查询”

### 已验证
- `backend/tests/agent/test_semantic_grounding.py`
- `backend/tests/semantic/test_tda_mql.py`
- `backend/tests/agent/test_executor_agent_v2.py`
- `backend/tests/agent/test_runtime_context.py`
- 结果：`38 passed, 1 warning`

### 下次恢复优先顺序
1. 先看 `design/EXPORT_REBATE_RECONCILIATION_V1.md` 末尾新增的“首跳入口修正”
2. 再看 `backend/app/mock/semantic_assets.py` 中 3 个出口退税相关资产
3. 最后看 `backend/app/agent/semantic_grounding.py` 的 `_is_entry_enabled` 和 `_score_model`

## 2026-03-31 出口退税数据已补入当前运行库
### 已完成
- 未走 `/api/v1/mock/generate` 全量清库重刷，而是定向向当前 PostgreSQL 库补入出口退税场景数据与语义模型。
- 已验证写入结果：
  - `recon_export_book_revenue_line` = 9
  - `recon_export_refund_tax_basis_line` = 9
  - `recon_export_contract_discount_line` = 4
  - 新增 5 个出口退税相关 `sys_semantic_model`

### 关键事实
- 前端语义模型页只展示数据库 `sys_semantic_model` 中已有记录，不会直接读取代码里的 `SEMANTIC_MODEL_RECORDS`。
- 因此“代码里已经有模型定义”并不代表前端立即可见，必须显式 seed 到当前运行库。

### 额外修复
- `generator.py` 中一条折扣样例的 `sync_status` 超过数据库字段长度，已改短以适配当前 PostgreSQL schema。

## 2026-03-31 前端已显式展示阶段级 LLM 调用证据
### 已完成
- 针对“像写死流程、看不到大模型调用过程”的反馈，已补前端展示：
  - `MultiAgentBoardRefresh.vue` 主界面直接显示当前阶段 LLM 调用证据卡片
  - `NavigatorRail.vue` 阶段卡显示 `LLM xN`
  - `InsightInspector.vue` 独立显示 `LLM Calls` 与 `Stage Reasoning`
- 注意：展示的是可审计的阶段摘要与调用证据，不是模型私有逐字思维链。

### 已验证
- `npm run build`（frontend）通过。
