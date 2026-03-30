# CODEX.md - 项目交接与恢复

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
