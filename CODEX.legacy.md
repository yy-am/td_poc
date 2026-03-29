# CODEX.md — 项目上下文与开发进展 (适用于任何AI助手恢复进度)

## 项目概述
**TDA-TDP 语义化智能问数 Agent 系统** — 企业级 POC 演示系统，向领导汇报。

核心功能：用户通过自然语言提问，ReAct Agent 调用工具查询数据库，实时展示思考-行动-观察推理链，最终生成分析结论和 ECharts 可视化图表。

业务场景：**税务-账务自动对账**（税局增值税申报数据 vs 会计利润表收入数据 的差异分析）。

## 技术栈
| 层 | 技术 |
|---|---|
| 前端 | Vue3 + TypeScript + Element Plus + ECharts + Pinia + Vite |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 |
| 数据库 | PostgreSQL 16 (需通过Docker或本地安装启动) |
| LLM | OpenAI协议统一客户端 (当前: deepseek-v3.2) |
| 通信 | WebSocket (Agent推理实时推送) + REST API |
| 包管理 | uv (Python), npm (前端) |

## LLM API
```
Base URL: https://jeniya.cn/v1
API Key:  sk-ooOP32Dy6I5kAl9YzIt6BuKyNCJKxytVCapPniwcRm8POqBT
Model:    deepseek-v3.2
```

## 环境
- Windows 11, bash shell (Git Bash)
- Node v24.14.0, npm 11.9.0
- Python 3.12.13 via uv (backend/.venv/)
- uv 0.11.2 (~/.local/bin/uv)
- Docker: **未安装** — 这是当前阻塞点

---

## 已完成的代码 (所有代码已写好，尚未运行)

### 后端 (backend/app/)
| 文件 | 作用 | 状态 |
|------|------|------|
| main.py | FastAPI入口, CORS, lifespan | 完成 |
| config.py | Pydantic Settings (.env读取) | 完成 |
| database.py | SQLAlchemy async engine + session | 完成 |
| models/__init__.py | 汇总导入28个ORM模型 | 完成,已验证 |
| models/enterprise.py | 3表: enterprise_info, bank_account, contact | 完成 |
| models/tax.py | 7表: vat_declaration, invoice_summary, cit_quarterly/annual, adjustment_items, other_taxes, risk_indicators | 完成 |
| models/accounting.py | 8表: chart_of_accounts, journal_entry/line, general_ledger, income_statement, balance_sheet, tax_payable_detail, depreciation_schedule | 完成 |
| models/reconciliation.py | 4表: revenue_comparison, tax_burden_analysis, adjustment_tracking, cross_check_result | 完成 |
| models/semantic.py | 6表: semantic_model, user_preference, industry, tax_type, conversation, conversation_message | 完成 |
| api/router.py | 路由汇总 | 完成 |
| api/chat.py | WebSocket /ws/chat/{session_id} | 完成 |
| api/sessions.py | 会话CRUD | 完成 |
| api/semantic.py | 语义模型CRUD + catalog | 完成 |
| api/datasource.py | 表列表, 表结构, SQL查询 | 完成 |
| api/preferences.py | 用户偏好 get/put | 完成 |
| api/mock_data.py | POST /mock/generate 生成数据 | 完成 |
| llm/client.py | 统一LLM客户端(AsyncOpenAI) | 完成 |
| mcp/tools/sql_executor.py | 4个MCP工具 + TOOL_DEFINITIONS | 完成 |
| agent/react_agent.py | ReAct循环核心(max 10步) | 完成 |
| agent/prompts.py | 系统提示词(含28表结构描述) | 完成 |
| mock/generator.py | Mock数据生成器(10企业×24月×28表) | 完成 |
| schemas/chat.py | Pydantic请求/响应模型 | 完成 |

### 前端 (frontend/src/)
| 文件 | 作用 | 状态 |
|------|------|------|
| main.ts | 入口(ElementPlus+Pinia+Router) | 完成 |
| App.vue | 主布局(暗色侧边栏+router-view) | 完成 |
| router/index.ts | 4路由: Chat/Semantic/Dashboard/Settings | 完成 |
| stores/chat.ts | Pinia会话状态管理 | 完成 |
| composables/useWebSocket.ts | WebSocket连接管理 | 完成 |
| types/agent.ts | AgentStep/ChatMessage/Session等类型 | 完成 |
| styles/global.css | 暗色主题全局样式 | 完成 |
| views/ChatView.vue | 问数工作台(会话列表+消息流+快捷问题) | 完成 |
| views/SemanticView.vue | 语义建模(物理/语义/指标三标签+详情抽屉) | 完成 |
| views/DashboardView.vue | 数据资产(统计卡片+表列表+结构弹窗) | 完成 |
| views/SettingsView.vue | 系统设置(LLM配置+Mock生成) | 完成 |
| components/chat/ThinkingProcess.vue | **核心组件**: ReAct推理步骤可视化 | 完成 |
| components/charts/ChartRenderer.vue | ECharts dark主题渲染器 | 完成 |

### 配置文件
| 文件 | 状态 |
|------|------|
| .env | 完成(含LLM API配置) |
| .gitignore | 完成 |
| docker-compose.yml | 完成(PostgreSQL 16) |
| backend/requirements.txt | 完成(依赖已安装到.venv) |
| frontend/package.json | 完成(依赖已安装到node_modules) |
| frontend/vite.config.ts | 完成(含/api和/ws代理) |
| scripts/init_db.py | 完成(建表+灌Mock数据) |

---

## 当前阻塞点

### 1. PostgreSQL 未启动
Docker Desktop 未安装。需要以下之一:
- **方案A**: 安装Docker Desktop → `docker-compose up -d`
- **方案B**: 切换为SQLite — 修改 `.env` 中 `DATABASE_URL=sqlite+aiosqlite:///./tda_tdp.db`，需 `uv pip install aiosqlite`，并调整 `datasource.py` 中的 information_schema 查询语法
- **方案C**: 本地安装 PostgreSQL

### 2. 数据库初始化未运行
数据库启动后需执行:
```bash
cd backend
export PATH="$HOME/.local/bin:$PATH"
.venv/Scripts/python.exe ../scripts/init_db.py
```

---

## 下一步工作

### 紧急 (让系统能跑起来)
1. 解决数据库问题 (Docker/SQLite/本地PG)
2. 运行 init_db.py 灌入Mock数据
3. 启动后端: `.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000`
4. 启动前端: `cd frontend && npm run dev`
5. 端到端测试: 打开 http://localhost:5173, 输入问题测试ReAct流程

### Phase 3: 语义层 (尚未编码)
- 创建 YAML 语义模型定义文件 (backend/app/semantic/definitions/)
- 实现语义编译器 (backend/app/semantic/compiler.py) — YAML→SQL
- 实现 semantic_query MCP工具
- 前端SemanticView: 添加血缘关系图 (ECharts关系图)

### Phase 4: RAG知识库 (尚未编码)
- ChromaDB设置 (backend/app/rag/vector_store.py)
- 知识文档编写 (knowledge/目录)
- 文档分块+索引
- 前端KnowledgeView

### Phase 5: 完善 (尚未编码)
- 用户偏好自动补全
- 高级分析Skill (异常检测、趋势预测、对账桥接)
- 端到端演示场景打磨

---

## 关键架构说明

### ReAct Agent 流程
```
用户提问 → WebSocket → ReactAgent.run()
  → 构建system_prompt(含28表结构+税务知识)
  → for step in range(10):
      → LLM推理(含tool_calls)
      → yield ThinkingStep    ← 前端实时显示思考过程
      → 如果有tool_call:
          → yield ActionStep  ← 前端显示调用哪个工具
          → 执行工具(sql_executor等)
          → yield ObservationStep ← 前端显示数据表格
          → 循环继续
      → 如果无tool_call:
          → yield AnswerStep  ← 前端显示最终答案+图表
          → break
```

### WebSocket消息格式
```json
{
  "type": "thinking|action|observation|answer|chart|table|error|status",
  "step_number": 1,
  "content": "文本内容",
  "metadata": {
    "tool_name": "sql_executor",
    "tool_input": {"query": "SELECT ..."},
    "chart_config": { /* ECharts option */ },
    "table_data": {"columns": [...], "rows": [...]}
  },
  "is_final": false
}
```

### Mock数据设计特点
- **10家企业**: 华兴科技、明达制造、锦程贸易、宏基建设、瑞丰金融、绿源环保、盛世传媒、天和医药、鑫隆商贸(异常)、卓越教育
- **故意差异**: 收入时间性差异(3-8%)、视同销售(明达/锦程)、折旧方法差异、坏账准备差异
- **异常企业**: 鑫隆商贸 — 隐瞒5-12%收入，税负率显著低于行业平均
- **季节性**: 制造业Q4高峰、零售业Q1高峰
- **约29000+行数据**
