# CLAUDE.md — 项目上下文与开发进展

## 项目信息
- **项目名称**: TDA-TDP 语义化智能问数 Agent 系统 (POC)
- **目录**: D:\lsy_projects\tda_tdp_poc
- **目标**: 企业级演示系统，向领导汇报，展示 ReAct Agent 思考推理 + 语义建模 + 动态可视化
- **核心场景**: 税务结果数据与账务数据自动对账（税局税金 vs 会计核算税金）

## 用户偏好
- **前端技术栈**: Vue3 + Element Plus + ECharts + Vite + TypeScript + Pinia
- **后端技术栈**: Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2
- **数据库**: PostgreSQL（首选），但当前环境 Docker 不可用，需要先解决 PG 问题或临时切换 SQLite
- **语言**: 代码注释/文档用中文，变量/函数名用英文
- **包管理**: 后端用 uv (已安装), 前端用 npm

## LLM API 配置
- **Base URL**: https://jeniya.cn/v1
- **API Key**: sk-ooOP32Dy6I5kAl9YzIt6BuKyNCJKxytVCapPniwcRm8POqBT
- **Model**: deepseek-v3.2
- **协议**: OpenAI compatible
- **配置文件**: .env (项目根目录)

## 环境信息
- **OS**: Windows 11, shell为bash (Git Bash)
- **Node**: v24.14.0, npm 11.9.0
- **Python**: 3.12.13 (通过uv安装，位于 backend/.venv/)
- **uv**: 0.11.2 (位于 ~/.local/bin/uv)
- **Docker**: 未安装/未运行 — PostgreSQL 需要外部启动或切换SQLite

## 关键设计决策
1. **ReAct Agent 模式**: 必须在前端展示思考/行动/观察循环，让领导看到AI推理过程
2. **28张数据表**: Mock数据29000+行，不得将结果写死在前端，必须调用大模型
3. **MCP Tools**: sql_executor, metadata_query, chart_generator, knowledge_search（以函数形式注册，同时支持MCP协议）
4. **WebSocket**: 实时推送 Agent 推理步骤 (`/ws/chat/{session_id}`)
5. **语义层**: YAML定义 → SQL编译器 → Headless BI
6. **RAG**: ChromaDB 存储税务法规/会计准则
7. **图表**: ECharts 动态配置，由Agent通过chart_generator工具生成

---

## 当前进展 (截至 2026-03-29)

### 已完成
- [x] **系统设计方案** — DESIGN.md (完整架构、28张表设计、API接口、前端原型)
- [x] **Python环境** — uv + Python 3.12 + venv + 所有依赖已安装
- [x] **后端骨架** — FastAPI应用完整结构:
  - `backend/app/main.py` — FastAPI入口，CORS，lifespan
  - `backend/app/config.py` — Pydantic Settings 配置
  - `backend/app/database.py` — SQLAlchemy async engine + session
  - `backend/app/models/` — **28张表的ORM模型全部完成** (enterprise, tax, accounting, reconciliation, semantic)
  - `backend/app/api/` — REST API路由全部完成 (sessions, semantic, datasource, preferences, mock_data)
  - `backend/app/api/chat.py` — WebSocket聊天端点
  - `backend/app/llm/client.py` — 统一LLM客户端（OpenAI协议）
  - `backend/app/mcp/tools/sql_executor.py` — MCP工具集 (sql_executor, metadata_query, chart_generator, knowledge_search)
  - `backend/app/agent/react_agent.py` — **ReAct Agent核心循环** (思考→行动→观察)
  - `backend/app/agent/prompts.py` — 系统提示词（含完整表结构描述）
  - `backend/app/mock/generator.py` — **完整的Mock数据生成器** (10企业×24月，含故意差异)
  - `backend/app/schemas/chat.py` — Pydantic schemas
- [x] **前端骨架** — Vue3完整应用:
  - `frontend/src/App.vue` — 主布局（暗色主题侧边栏）
  - `frontend/src/router/index.ts` — 路由 (Chat/Semantic/Dashboard/Settings)
  - `frontend/src/views/ChatView.vue` — **问数工作台** (会话列表+消息流+快捷问题)
  - `frontend/src/views/SemanticView.vue` — 语义建模管理 (物理/语义/指标三标签)
  - `frontend/src/views/DashboardView.vue` — 数据资产总览 (统计卡片+表列表)
  - `frontend/src/views/SettingsView.vue` — 系统设置 (LLM配置+Mock生成)
  - `frontend/src/components/chat/ThinkingProcess.vue` — **ReAct推理步骤可视化组件** (核心)
  - `frontend/src/components/charts/ChartRenderer.vue` — ECharts渲染组件
  - `frontend/src/composables/useWebSocket.ts` — WebSocket连接管理
  - `frontend/src/stores/chat.ts` — Pinia会话状态管理
  - `frontend/src/types/agent.ts` — TypeScript类型定义
  - `frontend/src/styles/global.css` — 暗色全局样式
- [x] **配置文件**: .env, docker-compose.yml, .gitignore, requirements.txt, vite.config.ts
- [x] **初始化脚本**: scripts/init_db.py
- [x] **模型导入验证**: 28张表全部正确导入

### 待完成 — 阻塞点
- [ ] **数据库启动**: Docker未安装，PostgreSQL无法启动。需要：
  - 方案A: 安装Docker Desktop → `docker-compose up -d` → 运行 init_db.py
  - 方案B: 将 DATABASE_URL 切换为 SQLite (`sqlite+aiosqlite:///./tda_tdp.db`)，需 `pip install aiosqlite`，并调整少量SQL语法
  - 方案C: 本地安装 PostgreSQL

### 待完成 — 后续Phase
- [ ] **Phase 1 收尾**: 启动数据库 + 运行init_db.py灌数据 + 验证后端API + 验证前端页面
- [ ] **Phase 2**: 端到端测试ReAct Agent (需LLM API可用)
- [ ] **Phase 3**: 语义层YAML定义 + 语义编译器 + 前端血缘图
- [ ] **Phase 4**: ChromaDB + RAG文档索引 + 前端KnowledgeView
- [ ] **Phase 5**: 用户偏好系统 + 高级分析Skill + 端到端演示

---

## 文件结构
```
tda_tdp_poc/
├── DESIGN.md              # 完整设计方案
├── CLAUDE.md              # 本文件 - Claude开发上下文
├── CODEX.md               # Codex开发上下文 (内容一致)
├── .env                   # 环境变量 (LLM API Key等)
├── .gitignore
├── docker-compose.yml     # PostgreSQL容器
│
├── backend/
│   ├── .venv/             # Python虚拟环境 (uv创建)
│   ├── requirements.txt   # Python依赖
│   └── app/
│       ├── __init__.py
│       ├── main.py        # FastAPI入口
│       ├── config.py      # 配置管理
│       ├── database.py    # 数据库连接
│       ├── api/
│       │   ├── router.py      # 路由汇总
│       │   ├── chat.py        # WebSocket /ws/chat/{session_id}
│       │   ├── sessions.py    # 会话CRUD
│       │   ├── semantic.py    # 语义模型CRUD
│       │   ├── datasource.py  # 数据表/Schema查询
│       │   ├── preferences.py # 用户偏好
│       │   └── mock_data.py   # Mock数据生成API
│       ├── agent/
│       │   ├── react_agent.py # ReAct循环核心 (MAX_STEPS=10)
│       │   ├── prompts.py     # 系统提示词
│       │   └── skills/        # 高级分析Skill (待实现)
│       ├── llm/
│       │   └── client.py      # 统一LLM客户端 (OpenAI协议)
│       ├── mcp/
│       │   └── tools/
│       │       └── sql_executor.py  # 4个MCP工具 + TOOL_DEFINITIONS
│       ├── models/
│       │   ├── __init__.py    # 汇总导入所有28个模型
│       │   ├── base.py        # DeclarativeBase + TimestampMixin
│       │   ├── enterprise.py  # 3表: enterprise_info/bank/contact
│       │   ├── tax.py         # 7表: vat/cit/other/risk
│       │   ├── accounting.py  # 8表: chart/journal/ledger/income/balance/tax_payable/depreciation
│       │   ├── reconciliation.py  # 4表: revenue_comparison/tax_burden/adjustment/cross_check
│       │   └── semantic.py    # 6表: semantic_model/preference/industry/tax_type/conversation/message
│       ├── schemas/
│       │   └── chat.py        # Pydantic请求/响应模型
│       ├── mock/
│       │   └── generator.py   # 完整Mock数据生成器 (10企业×24月)
│       ├── semantic/          # 语义层 (待实现)
│       └── rag/               # RAG知识库 (待实现)
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts     # 含代理配置 (/api→:8000, /ws→ws)
│   ├── tsconfig.json
│   └── src/
│       ├── main.ts            # 入口 (ElementPlus+Pinia+Router)
│       ├── App.vue            # 主布局 (侧边栏+路由视图)
│       ├── router/index.ts    # 4个路由
│       ├── stores/chat.ts     # Pinia会话状态
│       ├── composables/useWebSocket.ts  # WebSocket管理
│       ├── types/agent.ts     # TypeScript类型
│       ├── styles/global.css  # 暗色主题全局样式
│       ├── views/
│       │   ├── ChatView.vue       # 问数工作台 (核心页面)
│       │   ├── SemanticView.vue   # 语义建模管理
│       │   ├── DashboardView.vue  # 数据资产总览
│       │   └── SettingsView.vue   # 系统设置
│       └── components/
│           ├── chat/
│           │   └── ThinkingProcess.vue  # ReAct推理步骤可视化 (核心组件)
│           └── charts/
│               └── ChartRenderer.vue   # ECharts渲染器
│
├── knowledge/             # RAG知识文档 (待创建内容)
│   ├── tax_regulations/
│   ├── accounting_standards/
│   └── reconciliation_guides/
│
└── scripts/
    └── init_db.py         # 建表+灌Mock数据脚本
```

## 启动步骤 (数据库就绪后)
```bash
# 1. 启动PostgreSQL
docker-compose up -d

# 2. 初始化数据库 (建表+灌数据)
cd backend
.venv/Scripts/python.exe ../scripts/init_db.py

# 3. 启动后端
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# 4. 启动前端
cd ../frontend
npm run dev
```

## 注意事项
- 问数结果必须通过调用大模型生成，不可写死
- Mock数据包含故意差异(时间性差异3-8%、视同销售、折旧方法差异、坏账准备差异、1家异常企业)
- 前端需实时展示Agent推理过程(ReAct模式的thinking/action/observation)
- 所有对话通过WebSocket传输
- `uv` 路径: ~/.local/bin/uv, 使用前需 `export PATH="$HOME/.local/bin:$PATH"`
