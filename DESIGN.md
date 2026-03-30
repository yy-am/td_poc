# 语义化智能问数 Agent 系统 — 完整设计方案

## Context
为企业数据中台构建一套"语义化智能问数 Agent 系统"，核心场景为**税务-账务自动对账**。系统面向领导汇报演示，需展示 ReAct Agent 的思考推理过程、语义建模能力和动态可视化。

## 技术选型
- **后端**: Python + FastAPI + SQLAlchemy 2.0 (async) + Alembic
- **前端**: Vue3 + Element Plus + ECharts + Vite
- **数据库**: PostgreSQL 16
- **LLM**: OpenAI协议统一客户端 (支持GPT/GLM/DeepSeek), 当前使用 deepseek-v3.2
- **向量库**: ChromaDB (PersistentClient)
- **MCP**: FastMCP (Python SDK, in-process调用)

---

## 系统拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                    Vue3 Frontend (Vite:5173)                  │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────┐ │
│  │ 问数工作台│ │语义建模管理  │ │知识库管理 │ │系统设置   │ │
│  │ (WebSocket)│ │  (REST API) │ │(REST API) │ │(REST API) │ │
│  └─────┬────┘ └──────┬───────┘ └─────┬─────┘ └─────┬─────┘ │
└────────┼─────────────┼───────────────┼─────────────┼────────┘
         │ WS          │ HTTP          │ HTTP        │ HTTP
┌────────┼─────────────┼───────────────┼─────────────┼────────┐
│        ▼             ▼               ▼             ▼        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              FastAPI Application (:8000)               │   │
│  ├──────────┬──────────┬──────────┬──────────┬─────────┤   │
│  │ Multi-  │ Semantic │  MCP     │   RAG    │  User   │   │
│  │ Agent   │ Layer    │  Tools   │ Engine   │  Prefs  │   │
│  │Orchestr.│ Compiler │          │(ChromaDB)│         │   │
│  ├──────────┴─────┬────┴──────────┴──────────┴─────────┤   │
│  │                │                                     │   │
│  │    ┌───────────▼───────────┐   ┌──────────────┐     │   │
│  │    │  Unified LLM Client   │   │  PostgreSQL  │     │   │
│  │    │  (OpenAI Protocol)    │   │   28 Tables  │     │   │
│  │    └───────────────────────┘   └──────────────┘     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 数据模型设计 (28张表)

### A. 企业基础数据 (3张)
| # | 表名 | 说明 | 主要字段 |
|---|------|------|----------|
| 1 | `enterprise_info` | 企业主数据 | taxpayer_id(PK), enterprise_name, legal_representative, industry_code, registration_type, tax_authority, registered_capital, establishment_date, status |
| 2 | `enterprise_bank_account` | 银行账户 | id, taxpayer_id(FK), bank_name, account_number, account_type, is_primary |
| 3 | `enterprise_contact` | 联系地址 | id, taxpayer_id(FK), address, phone, email, financial_controller |

### B. 税务局端数据 (7张)
| # | 表名 | 说明 | 主要字段 |
|---|------|------|----------|
| 4 | `tax_vat_declaration` | 增值税申报主表 | id, taxpayer_id, tax_period, total_sales_amount, taxable_sales_amount, exempt_sales_amount, output_tax_amount, input_tax_amount, input_tax_transferred_out, tax_payable, declaration_date |
| 5 | `tax_vat_invoice_summary` | 发票汇总 | id, taxpayer_id, tax_period, invoice_type, invoice_count, total_amount, total_tax, total_amount_with_tax |
| 6 | `tax_cit_quarterly` | 所得税季度预缴 | id, taxpayer_id, tax_year, quarter, revenue_total, cost_total, profit_total, taxable_income, tax_rate, tax_payable, tax_prepaid |
| 7 | `tax_cit_annual` | 所得税年度汇算 | id, taxpayer_id, tax_year, accounting_profit, tax_adjustments_increase, tax_adjustments_decrease, taxable_income, tax_rate, tax_amount, tax_prepaid, tax_refund_or_due |
| 8 | `tax_cit_adjustment_items` | 纳税调整明细 | id, annual_id(FK), item_code, item_name, accounting_amount, tax_amount, adjustment_amount, adjustment_direction |
| 9 | `tax_other_taxes` | 其他税种 | id, taxpayer_id, tax_period, tax_type, tax_basis, tax_rate, tax_amount |
| 10 | `tax_risk_indicators` | 风险指标 | id, taxpayer_id, tax_period, indicator_code, indicator_name, indicator_value, threshold_value, risk_level, alert_message |

### C. 账务数据 (8张)
| # | 表名 | 说明 | 主要字段 |
|---|------|------|----------|
| 11 | `acct_chart_of_accounts` | 会计科目表 | id, account_code, account_name, account_type, parent_code, level, is_leaf, direction |
| 12 | `acct_journal_entry` | 凭证表头 | id, taxpayer_id, entry_number, entry_date, period, description, created_by, is_adjusted |
| 13 | `acct_journal_line` | 凭证明细 | id, entry_id(FK), account_code, sub_account, debit_amount, credit_amount, currency, description |
| 14 | `acct_general_ledger` | 总账余额 | id, taxpayer_id, account_code, period, opening_balance, debit_total, credit_total, closing_balance |
| 15 | `acct_income_statement` | 利润表 | id, taxpayer_id, period, revenue_main, revenue_other, cost_main, cost_other, tax_surcharges, selling_expenses, admin_expenses, finance_expenses, investment_income, non_operating_income, non_operating_expense, profit_total, income_tax_expense, net_profit |
| 16 | `acct_balance_sheet` | 资产负债表 | id, taxpayer_id, period, cash, receivables, inventory, fixed_assets, total_assets, payables, tax_payable_bs, total_liabilities, paid_in_capital, retained_earnings, total_equity |
| 17 | `acct_tax_payable_detail` | 应交税费明细 | id, taxpayer_id, period, tax_type, opening_balance, accrued_amount, paid_amount, closing_balance |
| 18 | `acct_depreciation_schedule` | 折旧台账 | id, taxpayer_id, asset_id, asset_name, category, original_value, acct_useful_life, acct_method, acct_depreciation_monthly, tax_useful_life, tax_method, tax_depreciation_monthly, difference_monthly |

### D. 对账分析 (4张)
| # | 表名 | 说明 | 主要字段 |
|---|------|------|----------|
| 19 | `recon_revenue_comparison` | 收入对比 | id, taxpayer_id, period, vat_declared_revenue, cit_declared_revenue, acct_book_revenue, vat_vs_acct_diff, cit_vs_acct_diff, vat_vs_cit_diff, diff_explanation |
| 20 | `recon_tax_burden_analysis` | 税负分析 | id, taxpayer_id, period, industry_code, vat_burden_rate, cit_effective_rate, total_tax_burden, industry_avg_vat_burden, industry_avg_cit_rate, deviation_vat, deviation_cit |
| 21 | `recon_adjustment_tracking` | 调整追踪 | id, taxpayer_id, period, adjustment_type, source_category, accounting_amount, tax_amount, difference, deferred_tax_impact |
| 22 | `recon_cross_check_result` | 交叉核验 | id, taxpayer_id, period, check_rule_code, check_rule_name, expected_value, actual_value, difference, status, recommendation |

### E. 系统元数据 (6张)
| # | 表名 | 说明 |
|---|------|------|
| 23 | `sys_semantic_model` | 语义模型注册 |
| 24 | `sys_user_preference` | 用户偏好 |
| 25 | `dict_industry` | 行业字典 |
| 26 | `dict_tax_type` | 税种字典 |
| 27 | `sys_conversation` | 会话记录 |
| 28 | `sys_conversation_message` | 消息记录 |

### Mock数据规模
- 10家企业, 5个行业, 24个月(2023-01 ~ 2024-12)
- 含故意差异: 收入时间性差异(3-8%)、视同销售、折旧方法差异、坏账准备差异
- 1家异常企业(税负显著低于行业平均)
- 季节性模式: 制造业Q4高峰, 零售业Q1高峰
- 约29,000+行数据

### 表关系
```
enterprise_info (taxpayer_id)
    ├── 1:N ── tax_vat_declaration
    ├── 1:N ── tax_vat_invoice_summary
    ├── 1:N ── tax_cit_quarterly
    ├── 1:N ── tax_cit_annual ── 1:N ── tax_cit_adjustment_items
    ├── 1:N ── tax_other_taxes
    ├── 1:N ── tax_risk_indicators
    ├── 1:N ── acct_journal_entry ── 1:N ── acct_journal_line
    ├── 1:N ── acct_general_ledger
    ├── 1:N ── acct_income_statement
    ├── 1:N ── acct_balance_sheet
    ├── 1:N ── acct_tax_payable_detail
    ├── 1:N ── acct_depreciation_schedule
    ├── 1:N ── recon_revenue_comparison
    ├── 1:N ── recon_tax_burden_analysis
    ├── 1:N ── recon_adjustment_tracking
    └── 1:N ── recon_cross_check_result

acct_chart_of_accounts (account_code)
    ├── 1:N ── acct_journal_line
    └── 1:N ── acct_general_ledger
```

---

## 语义层设计 (Headless BI)

### 三层架构
1. **物理层 (Physical)**: 28张PostgreSQL物理表
2. **语义层 (Semantic)**: YAML定义的语义模型, 包含join关系、指标、维度
3. **消费层 (Consumption)**: Agent通过semantic_query工具查询, 语义编译器将指标/维度编译为SQL

### 语义模型示例
```yaml
models:
  - name: vat_declaration
    label: "增值税申报数据"
    table: tax_vat_declaration
    dimensions:
      - name: taxpayer_id / tax_period / enterprise_name / industry_code
    metrics:
      - name: total_sales_amount (SUM)
      - name: output_tax (SUM)
      - name: input_tax (SUM)
      - name: tax_payable (derived: output - input)
    joins:
      - model: enterprise_info, on: taxpayer_id
```

### 指标体系
- **基础指标**: 销售额、销项税、进项税、营业收入、营业成本、净利润
- **派生指标**: 增值税税负率、所得税有效税率、收入差异率、毛利率
- **复合指标**: 税负偏离度、对账差异率、跨期调整金额

---

## 2026-03-30 设计升级：大模型智能理解层 + 语义模型中心化

### 背景与问题
- 当前 `runtime_context.py` 主要依赖关键词匹配、正则提取和数据库元数据探测来识别问题类型、期间和候选资产。
- 这种方式适合简单 metadata / fact query，但对真实业务里的口语化问法、复杂对比链路、多实体约束和跨口径分析不够稳定。
- 当前 Agent 虽然已经接入 `semantic_query`，但语义模型更多只是 Executor 的可选工具，而不是 Planner 与 Executor 的共同业务契约。
- 在复杂税账对账、差异诊断、风险归因等场景下，如果缺少“语义模型作为中心锚点”的理解与规划机制，准确率和可解释性都难以稳定。

### 升级目标
1. 将当前规则型 `runtime_context` 升级为“LLM 理解 + 语义 grounding + 规则校验”的混合智能理解层。
2. 让语义模型从“可选查询工具”升级为“规划与执行的主锚点”。
3. 让 Planner 规划的是“业务语义任务”，而不只是“去某张表查字段”。
4. 让 Executor 默认走 `semantic_query`，仅在语义模型无法表达、需要明细穿透或做事实校验时回退到 `sql_executor`。
5. 保留 Reviewer 的质量把关和 replan 机制，但把审查重点扩展到“语义口径是否一致、证据是否完整”。

### 升级后的目标链路

```
用户问题
  → Semantic Asset Retrieval（召回候选语义模型/指标/维度/实体锚点）
  → Understanding Agent（大模型生成结构化业务理解）
  → Grounding Validator（校验理解结果能否落到真实语义资产）
  → Semantic-aware Planner（生成带 semantic_binding 的 plan_graph）
  → Semantic-first Executor（优先 semantic_query，必要时 SQL 补充/验证）
  → Reviewer（审查节点结果与最终结论）
```

### 新的职责边界

#### 1. Semantic Asset Retrieval
- 输入：用户问题、对话历史
- 输出：候选语义模型、候选指标、候选维度、可用实体解析键、时间字段与粒度、候选 source_table
- 说明：这一层不负责“理解问题”，只负责先把语义资产召回出来，避免 LLM 裸猜全库结构。

#### 2. Understanding Agent
- 输入：用户问题、对话历史、候选语义资产
- 输出：结构化 `understanding_result`
- 说明：这一层负责把自然语言问题理解成业务意图，而不是直接生成 plan。

#### 3. Grounding Validator
- 输入：`understanding_result`、语义模型目录、物理表 schema
- 输出：可执行的 grounding 结果、风险提示、必要的补充约束
- 说明：这一层校验“理解结果是否真的能落到已有语义资产上”，避免 Planner 按空想语义规划。

#### 4. Semantic-aware Planner
- 输入：用户问题、对话历史、`understanding_result`、grounding 结果
- 输出：带 `semantic_binding` 的 `plan_graph`
- 说明：Planner 默认围绕业务指标、维度、实体和对比关系来规划，而不是优先围绕物理表规划。

#### 5. Semantic-first Executor
- 输入：当前 plan node、`semantic_binding`、历史执行结果、grounding 结果
- 输出：真实工具调用结果
- 说明：优先 `semantic_query`，`sql_executor` 主要用于语义模型缺失、明细穿透、交叉核验和异常修复。

#### 6. Reviewer
- 输入：用户原始问题、当前节点结果、全局执行上下文
- 输出：节点 verdict + 最终报告
- 说明：除现有完整性/合理性审查外，还应审查语义口径一致性、对比对象是否完整、证据链是否闭环。

### UnderstandingResult 契约

`Understanding Agent` 的目标产物不是自由文本，而是结构化对象。建议采用如下契约：

```json
{
  "query_mode": "metadata|fact_query|analysis|reconciliation|diagnosis",
  "intent_summary": "一句话描述用户真实业务目标",
  "business_goal": "要解释/比较/核验的业务对象",
  "entities": {
    "enterprise_name": ["华兴科技"],
    "taxpayer_id": [],
    "tax_types": ["增值税"],
    "periods": ["2024-07", "2024-08", "2024-09"]
  },
  "dimensions": ["enterprise_name", "period"],
  "metrics": ["vat_declared_revenue", "acct_book_revenue", "vat_vs_acct_diff"],
  "comparisons": [
    {
      "left": "申报收入",
      "right": "账面收入",
      "operator": "diff"
    }
  ],
  "required_evidence": [
    "申报口径收入",
    "账面口径收入",
    "差异金额",
    "差异原因或桥接项"
  ],
  "candidate_models": ["reconciliation_dashboard", "vat_declaration"],
  "ambiguities": [],
  "confidence": "high"
}
```

### 语义模型升级方向

当前 `sys_semantic_model` + YAML 定义主要覆盖：
- 模型名、标签、描述
- source_table
- dimensions / metrics

这只能支持“查询”，不足以支撑“理解 + 规划”。升级后，语义模型需要额外承载：
- 指标别名、业务同义词
- 维度别名、常见问法
- 默认时间字段、默认粒度、可支持粒度
- 实体解析锚点，如 `enterprise_name -> taxpayer_id`
- 常见分析模式，如“对账”“差异归因”“趋势”
- 推荐可视化类型
- 口径说明、适用边界、约束条件
- 需要补充事实校验的场景

建议优先把这些元信息先扩展进 YAML，而不是第一阶段就扩 DB 字段：

```yaml
name: reconciliation_dashboard
label: 收入对账分析看板
table: recon_revenue_comparison
description: 用于税务申报收入与账面收入对比分析
business_terms:
  - 收入对账
  - 税账差异
  - 申报收入
  - 账面收入
intent_aliases:
  - 比较申报收入和账面收入
  - 分析收入差异
entities:
  enterprise:
    id_field: taxpayer_id
    name_field: enterprise_name
time:
  default_field: period
  supported_grains: [month, quarter]
analysis_patterns:
  - compare
  - reconciliation
  - diagnosis
dimensions:
  - name: taxpayer_id
    label: 纳税人识别号
    column: taxpayer_id
metrics:
  - name: vat_declared_revenue
    label: 增值税申报收入
    column: vat_declared_revenue
    agg: sum
```

### Plan 节点升级方向：引入 semantic_binding

为让语义模型真正进入 Planner 与 Executor 的契约层，`plan_graph.nodes[]` 建议新增可选字段 `semantic_binding`：

```json
{
  "id": "n2",
  "title": "查询 Q3 申报收入与账面收入",
  "kind": "query",
  "tool_hints": ["semantic_query", "sql_executor"],
  "semantic_binding": {
    "models": ["reconciliation_dashboard"],
    "metrics": ["vat_declared_revenue", "acct_book_revenue", "vat_vs_acct_diff"],
    "dimensions": ["period", "enterprise_name"],
    "filters": [
      {"field": "taxpayer_id", "op": "=", "value": "xxx"},
      {"field": "period", "op": "in", "value": ["2024-07", "2024-08", "2024-09"]}
    ],
    "grain": "month",
    "fallback_to_sql": true
  }
}
```

该字段的作用：
- Planner 显式声明本节点绑定的业务语义
- Executor 不再只依赖自然语言节点标题猜工具
- Reviewer 可以基于语义绑定检查“口径是否一致”

### 第一阶段落地边界

为控制改造风险，第一阶段先做“骨架到位、接口成形、默认兼容”：

1. 新增 `understanding_agent.py` 与对应 prompt
2. 在 `orchestrator.py` 中接入 `Understanding Agent`
3. 将 `runtime_context.py` 升级为“grounding + validator”，可消费 `understanding_result`
4. 扩展 Planner 输入，让其接收 `understanding_result`
5. 扩展 `plan_graph` 节点结构，保留 `semantic_binding`
6. 扩展 Executor 输入，让其能消费 `semantic_binding`
7. 保留原有规则提取作为 fallback，不在第一阶段删除

### 非第一阶段目标
- 暂不在第一阶段修改前端交互形态
- 暂不强制改造全部已有语义模型定义
- 暂不引入新的数据库字段迁移
- 暂不把 `sql_executor` 完全降级为禁用，只调整优先级与使用边界

---

## Agent 决策流程

### 当前架构：Planner + Executor + Reviewer 三智能体协作（2026-03-29 升级）

```
用户提问
    │
    ▼
┌─── Orchestrator (chat_v3.py → orchestrator.py) ──────────────┐
│                                                               │
│  ① Planner Agent (planner_agent.py)                          │
│     - 分析意图、识别领域                                      │
│     - 生成 DAG 计划图 (nodes + edges + 依赖关系)              │
│     - 标注每步的工具、数据源、预期产出                        │
│     - 输出: plan_graph + reasoning（推理过程）                │
│                                                               │
│  ② Executor Agent (executor_agent.py) — 按 DAG 拓扑序执行    │
│     - 读取当前 active node                                    │
│     - 调用工具 (metadata/sql/semantic/chart/知识库)            │
│     - 每步产出: action + observation                          │
│     - 遇到异常: 向 Orchestrator 报告                          │
│                                                               │
│  ③ Reviewer Agent (reviewer_agent.py) — 关键节点后触发        │
│     - 检查数据完整性（是否缺失关键字段/维度）                 │
│     - 检查数据合理性（数量级、正负、趋势）                    │
│     - 检查回答质量（是否回答了用户的问题）                    │
│     - 输出: approve / reject + 原因                           │
│     - reject → 回到 Planner 重规划（最多 2 次）               │
│                                                               │
│  ④ 最终汇总报告 (Reviewer.synthesize)                         │
│     - Markdown 答案 + 数据证据引用                            │
│     - ECharts 图表配置                                        │
│     - 保存到会话历史                                          │
└───────────────────────────────────────────────────────────────┘
```

### 旧架构（保留但不再注册）
- `chat.py → react_agent_v4.py`：单 agent ReAct 循环，最多 10 轮
- 相关文件仍保留在 codebase 中以备回退

### WebSocket 消息协议（多智能体版）
```json
{
  "type": "agent_start|plan|plan_update|thinking|action|observation|review|replan_trigger|answer|error|status",
  "agent": "planner|executor|reviewer|orchestrator",
  "step_number": 1,
  "content": "用户可见的中文说明",
  "metadata": {
    "plan_graph": { "title": "...", "nodes": [...], "edges": [...] },
    "reasoning": "Planner 的推理过程",
    "node_id": "对应 plan 的哪个节点",
    "tool_name": "sql_executor",
    "tool_input": {"query": "SELECT ..."},
    "tool_input_summary": "查询增值税申报主表的销项税额",
    "sql_preview": "SELECT ...",
    "result_summary": "共返回 28 行",
    "table_data": { "columns": [...], "rows": [...] },
    "chart_config": { /* ECharts option */ },
    "duration_ms": 150,
    "verdict": "approve|reject",
    "review_points": ["数据完整", "数值合理"],
    "issues": ["缺少 2024-12 数据"],
    "suggestions": ["补查最近一期"],
    "evidence": ["引用的数据证据"]
  },
  "timestamp": "2026-03-29T00:00:00Z",
  "is_final": false
}
```

### 重规划机制
```
Reviewer reject → Planner.replan(original_plan, review_feedback)
  → 保留已完成节点（status=completed）
  → 修改或替换被拒绝节点
  → 可能新增补充节点
  → 输出带 change_reason 的更新后 plan_graph
  → Executor 从第一个 pending 节点继续执行
  → 最多 2 次重规划，超过后强制进入最终汇总
```

---

## MCP Tools 设计

| Tool | 说明 | 适用场景 |
|------|------|----------|
| `sql_executor` | 只读SQL执行 | 复杂自定义查询 |
| `metadata_query` | 元数据查询 | 了解表结构、字段 |
| `semantic_query` | 语义层查询 | 通过指标/维度名查数据 |
| `chart_generator` | 生成ECharts配置 | 可视化结果 |
| `knowledge_search` | 知识库搜索 | 查询税务法规、会计准则 |

### 高级分析 Skill
- **异常对账分析**: Z-score + IQR 检测异常差异
- **趋势预测**: 线性回归 + 季节分解
- **对账桥接分析**: 瀑布图展示差异构成

> Skill与Tool的区别: Tool是原子操作(执行SQL/搜索), Skill是多步骤的业务分析流程, 内部编排多个Tool调用 + 统计计算。

---

## 前端功能模块

### 1. 问数工作台 (ChatView) — 多智能体双视图
- 左侧: 会话历史列表
- 中央: **MultiAgentBoard** 双视图容器
  - **时间轴 (AgentTimeline)** — 左 35%：纵向事件流，按 agent 角色分色（Planner 蓝/Executor 橙/Reviewer 绿）
  - **DAG 计划图 (PlanDAGView)** — 右 65%：实时展示 Planner 生成的 DAG，节点状态随执行更新
  - **详情面板 (AgentDetailPanel)** — 底部：点击时间轴或 DAG 节点展开，显示 SQL/表格/图表/审查结论
  - **最终回答区**：富文本 Markdown + ECharts 图表 + 数据证据引用
- 底部: 输入框 + 快捷问题模板
- 交互联动：时间轴点击 ↔ DAG 高亮 ↔ 详情面板展开

### 2. 语义建模管理 (SemanticView)
- 物理表列表 + 表结构预览
- 语义模型CRUD (创建/编辑/删除)
- 指标编辑器 (名称、表达式、格式)
- 维度编辑器
- 血缘关系图 (ECharts关系图)

### 3. 知识库管理 (KnowledgeView)
- 文档列表 + 上传
- 分块预览
- 相似度搜索测试

### 4. 数据资产总览 (DashboardView)
- 28张表统计信息
- 指标体系概览
- 快速查询模板卡片

### 5. 系统设置 (SettingsView)
- LLM模型配置 (Base URL, Key, Model)
- 用户偏好设置 (默认图表类型、日期范围、关注企业)

---

## REST API 接口

| Method | Path | 说明 |
|--------|------|------|
| WS | `/ws/chat/{session_id}` | Agent对话WebSocket |
| GET/POST | `/api/v1/sessions` | 会话列表/创建 |
| GET | `/api/v1/sessions/{id}/messages` | 消息历史 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| GET/POST/PUT/DELETE | `/api/v1/semantic/models` | 语义模型CRUD |
| GET | `/api/v1/semantic/models/{id}/metrics` | 指标列表 |
| GET | `/api/v1/semantic/models/{id}/dimensions` | 维度列表 |
| GET | `/api/v1/semantic/catalog` | 全量目录 |
| POST | `/api/v1/semantic/query` | 语义查询测试 |
| GET/POST/DELETE | `/api/v1/knowledge/documents` | 知识库管理 |
| POST | `/api/v1/knowledge/search` | 相似度搜索 |
| GET | `/api/v1/datasource/tables` | 数据表列表 |
| GET | `/api/v1/datasource/tables/{name}/schema` | 表结构 |
| GET/PUT | `/api/v1/preferences/{user_id}` | 用户偏好 |
| POST | `/api/v1/mock/generate` | 生成Mock数据 |
| GET | `/api/v1/health` | 健康检查 |

---

## 实施步骤

### Phase 1: 基础架构
1. 初始化Python项目 + FastAPI骨架
2. 初始化Vue3项目 (Vite + Element Plus + ECharts)
3. SQLAlchemy ORM 28张表
4. Mock数据生成器
5. docker-compose.yml

### Phase 2: 核心Agent
6. 统一LLM客户端
7. MCP Tools
8. ReAct Agent + WebSocket
9. 前端: ChatView + ThinkingProcess

### Phase 3: 语义层
10. YAML语义定义
11. 语义编译器
12. 前端: SemanticView

### Phase 4: RAG知识库
13. ChromaDB + 文档索引
14. 知识文档
15. 前端: KnowledgeView

### Phase 5: 完善
16. 用户偏好系统
17. 高级Skill
18. Dashboard + Settings
19. 端到端测试

---

## 2026-03-29 设计补充：多智能体架构与 Agentic 真实性原则

### 多智能体架构文件清单

| 文件 | 角色 |
|------|------|
| `backend/app/agent/orchestrator.py` | 三智能体调度器，协调 Planner→Executor→Reviewer 循环 |
| `backend/app/agent/planner_agent.py` | Planner 智能体：意图分析 + DAG 规划 + 重规划 |
| `backend/app/agent/executor_agent.py` | Executor 智能体：按 DAG 拓扑序执行工具 |
| `backend/app/agent/reviewer_agent.py` | Reviewer 智能体：审查数据质量 + 生成最终报告 |
| `backend/app/agent/prompts/planner_prompt.py` | Planner 的 system prompt |
| `backend/app/agent/prompts/executor_prompt.py` | Executor 的 system prompt |
| `backend/app/agent/prompts/reviewer_prompt.py` | Reviewer 的 system prompt |
| `backend/app/api/chat_v3.py` | 新版 WebSocket endpoint，调用 orchestrator |
| `frontend/src/components/chat/MultiAgentBoard.vue` | 双视图容器（时间轴 + DAG + 详情） |
| `frontend/src/components/chat/AgentTimeline.vue` | 时间轴：按 agent 角色分色 |
| `frontend/src/components/chat/PlanDAGView.vue` | DAG 计划图：实时节点状态更新 |
| `frontend/src/components/chat/AgentDetailPanel.vue` | 详情面板：SQL/表格/图表/审查结论 |

### Agentic 真实性原则
- 计划图必须来自模型真实生成的 `plan_graph.source = “llm”`，不得用 fallback/规则图伪装。
- 前端图谱只渲染 `plan_source=llm` 的计划图；fallback 只能显示为占位状态或错误说明。
- planner 需要保持”问题贴合”而不是”业务模板化”；例如元数据问题必须规划成元数据查询。
- 工具执行、SQL 解释、结果表和图表必须建立在真实 plan graph 已产生的前提上。
- 前端交互补充：即使真实计划图生成较慢（~12-18s），也必须先立即反馈占位状态。
- WebSocket 发送逻辑已改为 `pendingMessage` 可靠发送，避免首消息因握手慢而丢失。

### 三个 Agent 的 Prompt 设计要点
- **Planner**: 输入用户问题 + 对话历史 + 工具清单 + 表元信息摘要。输出 JSON plan_graph + reasoning。对账类问题自动拆分”取税务数据 → 取财务数据 → 交叉比对”。
- **Executor**: 输入当前节点 + 工具定义 + 历史执行结果。语义查询优先于原始 SQL。每次只执行一个 node。
- **Reviewer**: 输入用户原始问题 + 当前节点执行结果 + 全局上下文。审查数据完整性、合理性、逻辑一致性。最终审查确认回答是否解答了用户问题。
