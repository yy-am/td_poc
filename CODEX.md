# CODEX.md - 项目交接与恢复

## 2026-03-31 Agent Flow / Validation Update

- 新增根目录文档：`AGENT_FLOW_CURRENT.md`
  - 收敛了当前真实阶段表、时序图、大模型调用次数分析和改进建议
- 本轮落地两个关键改进：
  - `TDA-MQL` 草拟阶段现在会做正式校验，不合法会阻断在 `tda_mql_draft`
  - reviewer / synthesis 不再隐式兜底，失败会显式 reject 或 blocked
- 本轮新增或更新的关键测试：
  - `backend/tests/agent/test_reviewer_agent_v2.py`
  - `backend/tests/agent/test_orchestrator.py`
  - `backend/tests/agent/test_stage_graph_v1_lite_spec.py`
- 当前最新后端回归结果：`57 passed, 1 warning`
- 仍待后续实现的第三点：审查成本优化，方向是“规则先审，模型补审”

## 文档用途
本文件给 Codex 类助手使用，用于在新会话中快速恢复项目方案、当前真实状态、用户习惯和下一步建议。

## 项目概览
- 项目名称：TDA-TDP 语义化智能问数 Agent POC
- 项目目录：`D:\lsy_projects\tda_tdp_poc`
- 目标：做一个可演示的企业级问数系统，展示 ReAct Agent 推理、工具调用、语义建模和图表生成能力。
- 主要场景：税务申报数据与财务核算数据的自动对账、差异分析和风险提示。

## 当前真实状态
更新时间：2026-03-29（多智能体架构升级后）

### 架构现状
- **当前生效的聊天链路**：`backend/app/main.py → chat_v3.py → orchestrator.py`（Planner + Executor + Reviewer 三智能体协作）
- **旧链路状态**：历史 `chat_v2 / react_agent / 非 clean 前端组件` 已于 2026-03-30 清理出仓库，不再保留重复实现
- 数据库：PostgreSQL 16（`/api/v1/health` 返回 `dialect=postgresql`）
- LLM：deepseek-v3.2（通过 OpenAI 协议统一客户端）

### 已验证可用
- 主后端运行在 `http://127.0.0.1:8000`
- 前端运行在 `http://127.0.0.1:5173`
- `GET /api/v1/health` 返回正常
- `GET /api/v1/datasource/tables` 可返回 28 张表及行数
- `GET /api/v1/sessions` / `POST /api/v1/sessions` 可用
- 前端 `npm run build` 已成功
- 前端 `npx vue-tsc -b` 已成功
- 前端已切换到 MultiAgentBoard 双视图组件

### 2026-03-29 多智能体架构升级（本轮核心工作）

#### 后端新增文件
| 文件 | 角色 |
|------|------|
| `backend/app/agent/orchestrator.py` | 三智能体调度器，协调 Planner→Executor→Reviewer 循环 |
| `backend/app/agent/planner_agent.py` | Planner 智能体：意图分析 + DAG 规划 + 重规划 |
| `backend/app/agent/executor_agent.py` | Executor 智能体：按 DAG 拓扑序执行工具 |
| `backend/app/agent/reviewer_agent.py` | Reviewer 智能体：审查数据质量 + 生成最终报告 |
| `backend/app/agent/prompts/planner_prompt.py` | Planner 的 system prompt |
| `backend/app/agent/prompts/executor_prompt.py` | Executor 的 system prompt |
| `backend/app/agent/prompts/reviewer_prompt.py` | Reviewer 的 system prompt |
| `backend/app/api/chat_v3.py` | 新版 WebSocket endpoint |

#### 前端新增文件
| 文件 | 角色 |
|------|------|
| `frontend/src/components/chat/MultiAgentBoard.vue` | 双视图容器（时间轴左 + DAG 右 + 详情底） |
| `frontend/src/components/chat/AgentTimeline.vue` | 时间轴：按 agent 角色分色（蓝/橙/绿） |
| `frontend/src/components/chat/PlanDAGView.vue` | DAG 计划图：实时节点状态更新 |
| `frontend/src/components/chat/AgentDetailPanel.vue` | 详情面板：SQL/表格/图表/审查结论 |

#### 修改的文件
- `backend/app/main.py` — 路由从 chat_v2 切到 chat_v3
- `frontend/src/types/agent.ts` — 新增 AgentEvent 类型、agent 角色、review/replan 事件
- `frontend/src/views/ChatView.vue` — 从 ReActGraphBoard 切到 MultiAgentBoard

#### 复用的现有能力
- `plan_presentation.py` — plan graph 结构、签名比对、工具摘要
- `planner.py::parse_plan_json` — JSON 解析
- `registry_v2.py` — 工具定义和执行函数
- `llm/client.py` — LLM 客户端（三个 agent 共用）
- `ChartRenderer.vue` — ECharts 图表渲染
- Element Plus el-table — 数据表格

## 恢复项目时先做什么
1. 先读 `DESIGN.md`、`CODEX.md`、`CLAUDE.md`
2. 再读项目内 skill：`.codex/skills/project-progress-handoff/SKILL.md`
3. 如果用户显式提到 `$design-progress-sync`，同时按全局 skill 习惯执行
4. 先核对运行状态，再开始写代码，不要只相信旧计划
5. 优先复用已经验证通过的 SQLite 本地链路，不要默认回退到 PostgreSQL/Docker

## 快速核对命令
```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/datasource/tables
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173
```

## 若需要重启服务
优先把缓存、临时目录、运行产物都放在 D 盘项目目录下的 `.cache`。

后端参考：
```powershell
$env:TMP="D:\lsy_projects\tda_tdp_poc\.cache\tmp"
$env:TEMP="D:\lsy_projects\tda_tdp_poc\.cache\tmp"
$env:UV_CACHE_DIR="D:\lsy_projects\tda_tdp_poc\.cache\uv"
Set-Location "D:\lsy_projects\tda_tdp_poc"
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

前端参考：
```powershell
$env:TMP="D:\lsy_projects\tda_tdp_poc\.cache\tmp"
$env:TEMP="D:\lsy_projects\tda_tdp_poc\.cache\tmp"
$env:npm_config_cache="D:\lsy_projects\tda_tdp_poc\.cache\npm"
Set-Location "D:\lsy_projects\tda_tdp_poc\frontend"
npm run dev
```

## 仍未完成的工作
- **多智能体端到端联调**：orchestrator.py / chat_v3.py 后端已写好，前端双视图组件已创建，但尚未通过真实 WebSocket 端到端测试完整问答流程
- **重规划流程验证**：Reviewer reject → Planner replan → Executor 恢复执行的循环尚未在真实问答中触发验证
- **时间轴 ↔ DAG 联动调试**：点击时间轴节点高亮 DAG 对应节点、点击 DAG 节点滚动时间轴，需实际联调微调
- Phase 3：语义层 YAML 定义、语义编译器、`semantic_query` 真正落地
- Phase 4：RAG / ChromaDB / 知识文档索引
- Phase 5：用户偏好自动补全、更多分析技能、演示脚本打磨
- 技术债：项目里仍有部分历史乱码文件，但当前运行链路已通过新的 prompt/registry 绕开

## 用户习惯与约束
- 这是一个长期推进型项目，每次对话都要先恢复“项目方案 + 当前进展”
- 每次有实质进展后，都要回写 `CODEX.md` 和 `CLAUDE.md`
- 文档里要区分“已验证事实”和“下一步计划”，不能混写
- 尽量不要把缓存、临时文件、运行产物装到 C 盘；优先落在 D 盘项目目录
- 项目文档和注释以中文为主，代码标识符保持英文
- 不要把密钥直接抄进交接文档；敏感配置以 `.env` 为准
- 用户重视体验：不要一上来就执行工具，优先给用户可理解的计划全景图；工具、SQL、技能等执行内容要尽量带中文语义解释
- 用户不接受“步骤一条条把页面越撑越长并自动下拉”的体验；优先使用图谱化、原地更新式的交互
- 用户允许在合适时主动创建 subagent 并行处理子任务，以提升整体推进效率

## 技能沉淀
- 项目内 skill：`D:\lsy_projects\tda_tdp_poc\.codex\skills\project-progress-handoff`
- 全局 skill：`C:\Users\lsy\.codex\skills\design-progress-sync`
- 目标：固定“先恢复上下文，再做实现，关键设计变化回写文档，中断前更新进度”的协作习惯

## 备注
- 8003 / 8004 端口可能存在本轮联调留下的临时后端实例；主链路以 8000 为准

## 2026-03-29 多智能体架构升级（最新）

### 架构变更
- 从单 agent ReAct 循环升级为 **Planner + Executor + Reviewer** 三智能体协作架构
- 新增 `orchestrator.py` 调度三个智能体，支持 DAG 拓扑序执行和最多 2 次重规划
- 前端从 `ReActGraphBoard` 切换为 **MultiAgentBoard** 双视图（时间轴 + DAG 计划图 + 详情面板）
- WebSocket 事件协议扩展：新增 `agent` 字段（planner/executor/reviewer/orchestrator）和 `agent_start`/`review`/`replan_trigger` 事件类型
- **旧链路**（`chat.py → react_agent_v4.py`）仍保留但已不被 main.py 注册

### 已验证
- 后端启动正常：`/api/v1/health` 返回 PostgreSQL
- 前端构建通过：`npm run build` 成功
- 前端类型检查通过：`npx vue-tsc -b` 成功
- 已确认 `/chat` 路由已切回 `frontend/src/views/ChatView.vue`，不再误走旧的 `ChatView_v2.vue`
- 已新增 clean 版聊天展示组件：`MultiAgentBoardClean.vue` / `AgentTimelineClean.vue` / `PlanDAGViewClean.vue` / `AgentDetailPanelClean.vue`
- 已确认 `frontend/src/views/ChatView.vue` 直接引用 clean 版组件链路，避免旧乱码组件影响计划展示
- 本轮用户反馈“发送问数需求后没有看到 AI 计划”，排查结论是前端实际生效路由与文档描述不一致，根因已修正

### 尚未验证
- 多智能体 WebSocket 端到端完整问答（需实际发送问题测试 orchestrator 链路）
- 浏览器内实际发送一个问数请求后，是否稳定先出现计划图再出现执行过程和最终回答
- Reviewer reject → Planner replan 的重规划循环
- 时间轴 ↔ DAG 联动交互

## 继续推进建议
1. 先做多智能体端到端联调，确保 orchestrator 链路可正常走通
2. 再补对话记录管理体验：会话重命名、删除、搜索
3. 继续语义模型：YAML 编辑、Agent 优先走 `semantic_query` 的策略
## 2026-03-30 最新验证摘要

- 已确认当前项目 LLM 配置实际使用 `https://jeniya.cn/v1` + `deepseek-v3.2`。
- 已做脱离沙箱的直连探针，请求成功返回；因此 jeniya 连通性正常，`/v1` 不是多余配置。
- 后端新增运行时上下文层 `backend/app/agent/runtime_context.py`，会动态识别：
  - 查询类型（metadata / fact_query / analysis）
  - 企业候选与 taxpayer_id
  - 年度 / 季度 / 月份期间
  - 相关语义模型、事实表、真实表字段 schema
- `backend/app/agent/orchestrator.py` 现会在 Planner 前先发一条 `status` 事件，用户发送问题后可立刻看到系统已识别的查询类型、期间、企业和候选资产，不再长时间无反馈。
- 新增 `backend/app/agent/planner_agent_v2.py` 与 `backend/app/agent/prompts/planner_prompt_v2.py`：
  - Planner 不再只靠静态提示词猜测
  - 会基于 runtime_context 规划
  - 会对错误计划做一次自校验，拒绝把复杂分析误规划成纯 metadata 路径
- 新增 `backend/app/agent/executor_agent_v2.py` 与 `backend/app/agent/prompts/executor_prompt_v2.py`：
  - Executor 会拿到真实相关表 schema
  - SQL/工具失败后会基于报错和 schema 做一次自动修正重试
  - 对复杂分析场景默认优先事实数据，而不是 metadata_query

### 本轮已验证通过

- 简单问题：`当前系统里有多少张表？先给我计划，再回答。`
  - 首个 `status` 事件：约 0.33s
  - 首个真实 `plan` 事件：约 14.03s
  - 最终回答：约 36.81s
  - 结果正确：28 张表
- 复杂问题：`分析华兴科技2024年Q3增值税申报收入与会计账面的差异`
  - 首个 `status` 事件：约 0.34s
  - 首个真实 `plan` 事件：约 28.08s
  - 首次执行动作：约 35.52s
  - 最终回答：约 91.48s
  - 真实执行路径：
    - `enterprise_info` 解析企业
    - `recon_revenue_comparison` 查询 Q3 三个月收入差异事实
    - `recon_adjustment_tracking` 汇总差异构成
  - Reviewer 对关键查询与分析节点均给出 `approve`
  - 最终结论：
    - Q3 申报收入较账面收入少 `539,338.77` 元
    - 主要原因是时间性差异

### 仍未验证

- 浏览器里手工点击 `/chat` 的整条链路，本轮尚未做真人 UI 操作验证；当前只完成了后端 WebSocket 端到端验证。
- `chart_generator` 在复杂分析路径中的最终可视化展示，本轮未强制触发验证。

### 额外说明

- 之前有几次本地探针脚本被 PowerShell 中文编码污染，导致问句变成 `?`；这些结果都不应再相信。
- 用 `compileall` 做全量编译自检时，部分旧文件因为 `__pycache__` 写入权限报错；这不影响本轮新增主链路模块的导入和运行。主链路已通过真实 WebSocket 问答验证。
## 2026-03-30 最新交接补充

### 本轮已完成
- 修复前端地址写死问题：统一改为走运行时 API / WebSocket 基地址，不再写死 `localhost:8000`
- 聊天页增加初始化失败提示，不再静默卡住
- 新增 Reviewer v2，修复旧 Reviewer prompt 乱码与复杂问数最终总结超时后的糟糕兜底
- `backend/app/agent/orchestrator.py` 已切换到 Reviewer v2

### 本轮已验证
- `GET http://127.0.0.1:8000/api/v1/health` 正常，数据库为 PostgreSQL
- 前端源码中已无 `http://localhost:8000` / `ws://localhost:8000` 硬编码
- `frontend` 目录下 `npm run build` 已通过
- `http://127.0.0.1:5173/api/v1/sessions` 与 `http://localhost:5173/api/v1/sessions` 都返回 `200`
- 通过 `ws://127.0.0.1:5173/ws/chat/{session_id}` 的真实代理层联调，已确认能收到 `status -> plan -> action -> answer`
- 简单问题“当前系统里有多少张表？先给我计划，再回答。”约 10.95 秒收到 `plan`，最终答案正确返回 28 张表

## 2026-03-30 Phase 1（TDA-MQL）启动记录

### 本轮已完成
- 新增 v2 方案文档：
  - `design/DESIGN_V2_MQL_STAGEGRAPH.md`
  - `design/PHASE1_TDA_MQL.md`
- `DESIGN.md` 已增加 v2 文档入口说明
- 新增 `backend/app/semantic/mql.py`
  - 提供 `TDA-MQL` 编译与执行入口
  - 当前支持：`model_name + select + group_by + entity_filters + filters + time_context + drilldown`
  - 当前明确不支持：`compare / attribution / 隐式 SQL fallback`
- `backend/app/api/semantic_v2.py` 新增接口：
  - `POST /api/v1/semantic/mql/validate`
  - `POST /api/v1/semantic/mql/query`
- `backend/app/mcp/tools/registry_v2.py` 已新增 `mql_query` tool
- `backend/app/agent/executor_agent_v2.py`
  - 已支持在 `tool_hints=["mql_query"]` 或 `semantic_binding.query_language=tda_mql` 时显式走 `mql_query`
  - 对显式 `tda_mql` 绑定禁用隐藏 fallback，不会偷偷回退到 `sql_executor`
- `backend/app/agent/plan_presentation.py`
  - 已补 `mql_query` 的工具中文说明、输入摘要和结果摘要
- `backend/app/agent/semantic_grounding.py`
  - 指标语义强的复合分析模型会把 `recommended_tool` 标为 `mql_query`
- `backend/app/agent/runtime_context.py`
  - 计划校验已识别 `mql_query`
  - 运行时状态文案会把推荐工具标成 `MQL`
- 语义目录元数据已补齐：
  - `relationship_graph`
  - `metric_lineage`
  - `detail_fields`
  - `materialization_policy`
  - `query_hints`
- 税务对账领域新增语义资产：
  - `mart_revenue_timing_gap`
  - `mart_vat_payable_snapshot`
  - `mart_cit_adjustment_bridge`
- 当前语义资产总数已验证为 `25`

### 本轮已验证
- `backend/tests/semantic/test_tda_mql.py` 通过
- `backend/tests/agent/test_executor_agent_v2.py` 通过
- `backend/tests/agent/test_runtime_context.py` 通过
- `backend/tests/agent/test_semantic_grounding.py` 通过
- 合计 `20` 个测试通过
- `app.api.semantic_v2.router` 可正常导入，当前路由数为 `9`
- `app.mcp.tools.registry_v2.TOOL_FUNCTIONS` 已确认包含 `mql_query`

### 当前未做
- 尚未把 `TDA-MQL` 接入 orchestrator / planner / executor 主链
- Planner 仍未稳定地产出 `tool_hints=["mql_query"] + semantic_binding.query_language=tda_mql`
- 尚未开始 StageGraph 改造
- 尚未实现 `compare / attribution / Python analysis`

### 恢复建议
1. 先读 `design/DESIGN_V2_MQL_STAGEGRAPH.md` 和 `design/PHASE1_TDA_MQL.md`
2. 再读 `backend/app/semantic/mql.py`、`backend/app/mock/semantic_assets.py`
3. 用下列命令快速回归：
```powershell
Set-Location D:\lsy_projects\tda_tdp_poc\backend
.\.venv\Scripts\python.exe -m pytest tests/semantic/test_tda_mql.py tests/agent/test_runtime_context.py tests/agent/test_semantic_grounding.py
```

### 额外约束
- 用户明确要求：不要额外写“没要求的兜底逻辑”
- Phase 1 若能力未支持，应显式返回校验错误，不允许偷偷降级到原始 SQL
- 复杂问题“分析华兴科技2024年Q3增值税申报收入与会计账面的差异”约 26.77 秒收到 `plan`，中途经历一次 `replan`，约 128.59 秒收到最终完整报告；结论为 Q3 累计差异 `-540,338.77` 元，主要是时间性差异

### 当前最可信判断
- 用户之前在浏览器里“没反应”，高概率是因为页面入口使用了 `127.0.0.1:5173`，而前端把 API / WS 写死到 `localhost:8000`，再叠加后端 CORS 仅放行 `http://localhost:5173`，浏览器表现为静默卡住
- 当前这条链路已经通过真实代理联调自证修通，不再只是推测

### 下一步最直接恢复路径
1. 确认后端仍监听 `127.0.0.1:8000`
2. 确认前端开发服务器仍在 `127.0.0.1:5173`
3. 直接打开 `/chat`，必要时硬刷新
4. 若仍异常，优先查浏览器控制台与 Network 里的 `/api/v1/sessions`、`/sessions/{id}/messages`、`/ws/chat/{id}`

### 用户偏好
- 必须先自证链路跑通再交付，不接受“应该好了”
- 计划不能写死，必须是真正 agentic
- 必须区分“已验证”和“推测”

## 2026-03-30 文档补充

- 本轮新增 `PROJECT_CODE_GUIDE.md`，把当前项目按根目录、后端包、前端包、脚本目录、知识目录逐层梳理了一遍。
- 文档特别说明了当前主链路：
  - 后端：`main.py -> router_v2.py / chat_v3.py -> orchestrator.py`
  - 前端：`ChatView.vue -> useWebSocket.ts -> MultiAgentBoardClean.vue`
- 文档同时标记了 legacy 文件和占位目录，避免后续助手误把旧链路当成当前实现。
- 本轮未改动业务逻辑，只新增项目理解文档。

## 2026-03-30 冗余文件清理

### 本轮已完成
- 删除主链路外的历史源码：
  - 后端 API：`chat.py`、`chat_v2.py`、`chat_ws.py`、`router.py`、`semantic.py`、`mock_data.py`
  - 后端 Agent：第一代三智能体文件、`react_agent*`、旧 `system_prompt*`、旧 prompt 文件、旧 `registry.py`、旧 `semantic/service.py`
  - 前端：`ChatView_v2.vue`、`SemanticView.vue` 与非 clean 聊天展示组件
- 删除根目录和 `backend/` 下不再使用的本地 SQLite 测试库、历史日志、legacy 交接文档以及 `backend/app/**/__pycache__`
- 更新 `PROJECT_CODE_GUIDE.md`，把“仍保留的历史版本”改成“已完成清理”的现状描述

### 本轮已验证
- 当前入口引用仍然只走 `router_v2 + chat_v3 + orchestrator + *_v2 + *Clean.vue`
- `frontend/package.json` 的 `build` 脚本仍为 `vue-tsc -b && vite build`
- 当前 `.env` 仍指向 PostgreSQL；本轮删除的 SQLite 文件均为本地测试/运行残留，不是主链路数据库
- `frontend` 目录下重新执行 `npm run build` 成功
- 使用新的 Python 进程重新导入 `app.main`、`router_v2`、`chat_v3`、`orchestrator` 与 `*_agent_v2` 成功
- 本地 `GET /api/v1/health` 与 `GET /api/v1/datasource/tables` 均返回 `200`

### 当前未完成 / 风险
- `backend-server-8000.log` 与 `frontend-server.log` 因被运行中的进程占用，当前未能删除；不影响功能

## 2026-03-30 语义层升级（本轮）

### 本轮完成
- 语义资产目录升级为以 `semantic_kind` 为中心的分层语义目录，并新增 `backend/app/mock/semantic_assets.py`。
- 当前活动语义资产补齐为 22 个主模型：实体/维度 4 个、原子事实 13 个、复合分析 5 个；旧 20 个模型保留但已按兼容方式归档在 `sys_semantic_model` 中。
- 新增 `backend/app/semantic/compiler_v2.py`、`backend/app/semantic/service_v3.py`、`backend/app/semantic/catalog.py`，支持 `sources + joins`、表达式指标/维度、实体解析、`entity_filters / resolved_filters / grain`。
- `semantic_v2` API、MCP `semantic_query` 工具、Pydantic schema 已切到新契约。
- Understanding / Planner / Runtime Validator / Executor 已切到新语义契约：
  - `understanding_result` 新增 `semantic_scope`（`entity_models / atomic_models / composite_models`）
  - `semantic_binding` 新增 `entry_model / supporting_models / entity_filters / resolved_filters / fallback_policy`
  - Executor 新增 deterministic semantic-first 路径，优先直接调用 `semantic_query`。
- 前端已同步：
  - `frontend/src/views/SemanticView_v2.vue` 按 `entity_dimension / atomic_fact / composite_analysis` 展示模型
  - `frontend/src/components/chat/AgentDetailPanelClean.vue` 可展示语义绑定、业务过滤、已解析过滤
  - `frontend/src/types/agent.ts` 已升级到新 binding / semantic metadata 结构
- `frontend/tsconfig.app.json` 已排除 prototype-only 的 `ExecutionAtlasPrototypeView.vue` 与 `frontend/prototypes/**/*`，避免未并入主链的原型文件阻塞主应用构建。

### 本轮已验证
- `GET http://127.0.0.1:8000/api/v1/health` 返回正常，数据库仍为 PostgreSQL。
- 在后端 venv 中成功导入：`app.main`、新的 prompts、`understanding_agent.py`、`executor_agent_v2.py`、`runtime_context.py`。
- 已执行语义资产 seed：`sys_semantic_model` 从 20 条增长到 42 条（其中新 22 条为活动模型，旧模型归档保留）。
- 函数级语义查询验证通过：
  - `mart_tax_risk_alert` + `entity_filters.enterprise_name -> taxpayer_id` 解析成功，返回 `鑫隆商贸有限公司` 风险预警明细。
  - `mart_revenue_reconciliation` + `entity_filters.enterprise_name` + `period in [2024-07,08,09]` 成功返回 `华兴科技有限公司` 2024Q3 三个月收入对账结果。
- API 级验证通过（`FastAPI TestClient`）：
  - `/api/v1/semantic/catalog` 返回 `catalog_by_kind`
  - `/api/v1/semantic/query` 返回 `resolved_filters` 与 `resolution_log`
- 前端 `npm run build` 已通过。

### 当前未完成 / 风险
- 本轮没有重启正在运行的 `127.0.0.1:8000` 常驻后端进程；因此若该进程早于本轮修改启动，浏览器实际访问到的可能仍是旧进程。当前代码本身已通过 `app.main` 导入与 `TestClient` 验证。
- 未做真实 LLM 在线端到端问答回放；本轮重点验证的是语义资产、语义查询、契约与前端构建，而不是依赖外部模型服务的完整聊天链路。
- `DESIGN.md` 本身已有用户侧更新且当前工作区仍显示修改中，本轮未覆盖其内容。

### 最直接恢复路径
1. 如需验证浏览器真实效果，先重启后端到当前代码版本，再打开 `/chat` 与 `/semantic`。
2. 重点检查语义主链：`semantic_scope -> semantic_binding -> semantic_query -> resolved_filters`。
3. 用两个场景回归：
   - 风险预警：`查看鑫隆商贸有限公司的税务风险预警`
   - 收入对账：`分析华兴科技有限公司 2024 年 Q3 增值税申报收入与账面收入差异`
4. 若要继续收敛体验层，优先做运行中后端重启后的 UI 联调，而不是再回头改语义契约。

### 用户协作偏好（继续保持）
- 这次用户明确要求“一次性彻底搞完，不要总返工”，所以后续优先做闭环验证和收口，不要再拆成零碎补丁。
- 用户判断“语义模型使用太薄弱”是正确方向；后续所有问数主链都应继续坚持 semantic-first，而不是退回显式企业匹配 SQL 节点。
- 每轮有实质进展后都要继续回写 `CODEX.md` / `CLAUDE.md`。

## 2026-03-30 Phase 1 继续推进（Planner + 资产扩展）

### 本轮已完成
- `backend/app/agent/planner_agent_v2.py`
  - Planner 在命中 `recommended_tool=mql_query` 的复合语义资产时，会显式写入：
    - `tool_hints=["mql_query"]`
    - `semantic_binding.query_language="tda_mql"`
    - 推断出的 `time_context`
  - 同时收紧 binding seed：优先使用用户显式提到的 metrics / dimensions，不再默认把模型全部字段塞进查询绑定
- `backend/app/agent/prompts/planner_prompt_v3.py`
  - 已补充 prompt 契约：命中 `recommended_tool=mql_query` 时，Planner 应直接产出 MQL 路径
- `backend/app/agent/understanding_agent.py`
  - 修复 fallback 场景下候选模型为空的兼容性回归，保持旧测试契约
- `backend/app/mock/semantic_assets.py`
  - 新增 3 个税务对账主题资产：
    - `mart_cit_settlement_bridge`
    - `mart_vat_declaration_diagnostics`
    - `mart_depreciation_timing_difference`
  - 当前语义资产总数已增至 `28`
- `backend/tests/agent/test_planner_agent_v2.py`
  - 新增 Planner 显式 MQL 绑定测试
- `backend/tests/semantic/test_tda_mql.py`
  - 新增年度汇缴桥接资产与 year-grain MQL 编译测试
- 设计文档已同步：
  - `design/PHASE1_TDA_MQL.md`
  - `design/DESIGN_V2_MQL_STAGEGRAPH.md`

### 本轮已验证
- `Set-Location backend; .\.venv\Scripts\python.exe -m pytest`
  - 共 `28` 个测试通过
- 已确认新增语义资产被目录加载：
  - `mart_cit_settlement_bridge`
  - `mart_vat_declaration_diagnostics`
  - `mart_depreciation_timing_difference`

### 当前未做
- Planner 仍未通过真实 LLM 端到端问答稳定观察到每次都主动产出 `mql_query` 节点；本轮做的是“契约 + enrichment + 测试”层闭环
- 尚未开始 StageGraph 改造
- 尚未实现 compare / attribution / Python analysis

### 额外约束（继续保持）
- 用户明确要求：**不要写莫名其妙没要求的兜底逻辑**
- 当前 `TDA-MQL` 主路径对未支持能力仍采用“显式报错”，不做隐式 SQL fallback

### 下一步最直接路径
1. 用真实问句回归 Planner/Executor 主链，观察是否稳定先产出 `mql_query` 计划节点
2. 如果稳定，再开始 StageGraph v0 设计与最小实现
3. 若继续补 Phase 1，则优先增加更多税务对账 case 对应的 composite assets，而不是扩隐式能力

## 2026-03-30 StageGraph v0 与真实回归补充

### 本轮完成
- `backend/app/llm/client.py`
  - 新增仅针对 `APIConnectionError / APITimeoutError` 的瞬时重试
  - 没有新增任何语义 fallback 或 SQL fallback
- 真实 LLM 回归后，补强了税务对账语义检索：
  - `backend/app/agent/semantic_grounding.py`
  - `backend/app/agent/runtime_context.py`
  - `backend/app/mock/semantic_assets.py`
  - 新增/补强 `汇算清缴桥接`、`增值税申报诊断` 等 alias 与领域词
- `StageGraph v0` 已落地：
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

### 本轮已验证
- 真实 LLM 回归（改进后）：
  - `backend-live-planner-regression-escalated-v2.json`
  - 统计结果：`total_runs=6, llm_plan_runs=5, fallback_runs=1, mql_path_runs=5`
  - 收入差异问句：`2/2` 命中 `mql_query`
  - VAT 申报诊断：`2/2` 命中 `mql_query`
  - CIT 汇缴桥接：`1/2` 命中 `mql_query`
  - 剩余 1 次 miss 已定位为外部 `APIConnectionError`，不是语义路由偏差
- 后端全量测试：`37 passed, 1 warning`
- 前端 `npm run build`：已通过
  - 首次在沙箱内因环境级 `spawn EPERM` 失败
  - 提权重跑后通过，因此不是业务代码问题

### 当前最可信状态
- 可以认为：真实问句下，只要成功拿到 LLM 计划，Planner 已基本稳定走 MQL 主路径
- `StageGraph v0` 现在已经可见、可测、可在主链路里观察阶段推进
- 仍然没有加入用户未要求的隐藏兜底逻辑

### 尚未完成
- 尚未做浏览器真实 WebSocket 回归，确认 UI 中先显示 `StageGraph v0`、后显示真实 LLM `plan_graph`
- 尚未进入 `StageGraph v1` 的人工审核断点、暂停/恢复、阶段持久化

### 最直接恢复路径
1. 先看 `design/DESIGN_V2_MQL_STAGEGRAPH.md`
2. 再看 `backend/app/agent/stage_graph.py` 与 `backend/app/agent/orchestrator.py`
3. 跑后端测试：
```powershell
Set-Location D:\lsy_projects\tda_tdp_poc\backend
.\.venv\Scripts\python.exe -m pytest
```
4. 跑前端构建：
```powershell
Set-Location D:\lsy_projects\tda_tdp_poc\frontend
npm run build
```

## 2026-03-30 前端 StageGraph 视图对齐
### 本轮已完成
- `frontend/src/components/chat/MultiAgentBoardClean.vue`
  - 中间图组件已切换到 `PlanFlowDeckClean.vue`
- `frontend/src/components/chat/PlanFlowDeckClean.vue`
  - 现在是前端主链路的中间图组件
  - 优先展示 `StageGraph v0`
  - 保留真实 LLM `plan_graph` 的卡片化展示
- `design/agent-visual-prototypes/v7-right-inspector-bilingual.html`
  - 已按当前 6 段 StageGraph 调整关键视觉文案

### 本轮已验证
- `Set-Location frontend; npm run build`
  - 已通过
  - 本轮未再触发 `spawn EPERM`

### 当前最可信状态
- 前端真实展示链路现在使用的是 `PlanFlowDeckClean.vue`
- 中间图、左侧阶段条和右侧 Inspector 的主语言已经对齐到当前 `StageGraph v0`
- 本轮只改展示层，没有新增任何用户未要求的 fallback 逻辑

### 下一步最直接路径
1. 浏览器真实联调 `/chat`
2. 确认 UI 中先出现 `StageGraph v0`，再切到真实 LLM `plan_graph`
3. 通过后进入 `StageGraph v1` 的人工审核断点与暂停/恢复

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

## 2026-03-31 出口退税场景设计补充

### 本轮已完成
- 新增专项设计文档：
  - `design/EXPORT_REBATE_RECONCILIATION_V1.md`
- 设计目标是把“出口退税账面收入 vs 税基金额对账”从演示型月度结果表，重构成更接近企业真实场景的语义资产体系
- 设计明确引入三张核心事实表：
  - `fact_export_book_revenue_line`
  - `fact_export_refund_tax_basis_line`
  - `fact_export_contract_discount_line`
- 关键判断：
  - 现有 `mart_revenue_reconciliation` 适合通用收入对账，不适合作为出口退税证据链主入口
  - 合同折扣必须成为结构化第三张事实表，不能继续只放在 `diff_explanation` 或粗粒度调整汇总里
  - 出口退税场景至少需要区分 `book_period / rebate_period / export_date / discount_effective_date`
- 已同步更新：
  - `design/DESIGN_V2_MQL_STAGEGRAPH.md`
  - `design/PHASE1_TDA_MQL.md`
  - `design/PROJECT_PROGRESS_V2.md`

### 本轮未做
- 未新增 ORM 模型
- 未改 `backend/app/mock/generator.py`
- 未把新资产接入 `backend/app/mock/semantic_assets.py`
- 未做任何后端测试或前端构建验证

### 当前最可信状态
- 这轮属于“设计定稿并回写主文档”，不是“代码已落地”
- 后续如果进入实现，优先从三张事实表和 `mart_export_rebate_reconciliation` 开始，而不是再扩一张月度结果表

### 最直接恢复路径
1. 先看 `design/EXPORT_REBATE_RECONCILIATION_V1.md`
2. 再看 `design/DESIGN_V2_MQL_STAGEGRAPH.md`
3. 若开始实现，优先补：
   - ORM 模型
   - mock 数据
   - semantic assets
   - 真实问句回归

## 2026-03-31 出口退税场景已落代码
### 本轮完成
- 已把设计稿真正落到后端：
  - ORM：`recon_export_book_revenue_line / recon_export_refund_tax_basis_line / recon_export_contract_discount_line`
  - mock：出口退税账面收入 / 税基 / 折扣单证链
  - semantic assets：`fact_*` + `mart_export_rebate_reconciliation` + `mart_export_discount_bridge`
  - MQL：`time_context.role` 已可驱动 `book_period / rebate_period / export_date / discount_effective_date`
- 用户已明确要求不要通过写死场景文件来做分析；这一轮实现遵守该约束，仍然走前端问句 -> agent -> semantic path 动态分析

### 验证
- `backend/tests/semantic/test_tda_mql.py`
- `backend/tests/agent/test_semantic_grounding.py`
- `backend/tests/agent/test_executor_agent_v2.py`
- `backend/tests/agent/test_runtime_context.py`
- 结果：`28 passed, 1 warning` + `7 passed`

## 2026-03-31 出口退税语义入口修正
### 本轮变化
- 用户明确指出“合同折扣桥接主题”不应作为企业真实场景中的首跳入口。
- 现已按该要求修正：
  - `mart_export_rebate_reconciliation` 作为首跳主题
  - `fact_export_contract_discount_line` 作为二跳折扣记录查询
  - `mart_export_discount_bridge` 保留为支持性分析主题，并设置 `entry_enabled=false`
- `backend/app/agent/semantic_grounding.py` 已增加入口偏好降权逻辑，避免普通对账问句优先命中折扣支持主题。

### 已验证
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/agent/test_semantic_grounding.py backend/tests/semantic/test_tda_mql.py backend/tests/agent/test_executor_agent_v2.py backend/tests/agent/test_runtime_context.py -q`
- 结果：`38 passed, 1 warning`

### 恢复提示
- 如果后续继续优化这个场景，优先看：
  1. `backend/app/mock/semantic_assets.py`
  2. `backend/app/agent/semantic_grounding.py`
  3. `backend/tests/agent/test_semantic_grounding.py`

## 2026-03-31 出口退税数据已补入当前运行库
### 本轮实际操作
- 未全量重刷 mock 数据，仅定向向当前 PostgreSQL 运行库补入出口退税场景数据。
- 已插入：
  - `recon_export_book_revenue_line`: 9 行
  - `recon_export_refund_tax_basis_line`: 9 行
  - `recon_export_contract_discount_line`: 4 行
- 已补入 5 个出口退税相关语义模型记录到 `sys_semantic_model`

### 现场验证
- 当前运行库 `sys_semantic_model` 原本无任何 `export / 出口退税` 相关记录，所以前端页面看不到不是前端过滤，而是数据库未种入。
- 前端 `SemanticView_v2` 读取的是 `/api/v1/semantic/catalog`，而该接口直接查 `sys_semantic_model`。

### 顺手修复
- `backend/app/mock/generator.py` 中折扣样例状态 `book_only_pending_tax` 超过了数据库 `sync_status VARCHAR(20)` 限制。
- 已改为 `book_pending_tax`，否则对当前 PostgreSQL 库执行插入会失败。

## 2026-03-31 前端已显式展示阶段级 LLM 调用证据
### 本轮变化
- 用户反馈当前前端只给阶段名和结果，不足以证明真实调用了大模型，容易看起来像写死流程。
- 已将“阶段摘要 + LLM 调用证据”直接暴露到主工作台与 Inspector：
  - 主工作台新增 `LLM Trace` 区块，默认展示当前阶段的模型调用次数、prompt 摘要、模型返回摘要。
  - 左侧阶段导航新增 `LLM xN` 标记。
  - Inspector 默认展开阶段摘要，并新增独立 `LLM Calls` 区块。
- 后端本来就有 LLM trace：`LLMClient.begin_trace/end_trace` + orchestrator `stage_llm_traces`，这轮主要是前端可视化补齐。

### 已验证
- `npm run build`（frontend）通过。
