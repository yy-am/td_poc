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

## 2026-03-30 v2 方案入口

围绕 `TDA-MQL + StageGraph + 税务对账领域知识层` 的新方案已单独沉淀到：

- `design/DESIGN_V2_MQL_STAGEGRAPH.md`
- `design/PHASE1_TDA_MQL.md`

当前 `DESIGN.md` 仍保留现状和已有实现说明；v2 文档作为下一阶段演进方案的主入口。

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

## 语义层设计 (Tax Warehouse Governance)

### 核心定位
- 语义模型不是“给报表起个名字的 YAML”，而是 Agent、数据资产和业务口径之间的正式契约。
- 语义层必须完整覆盖治理后的核心数据资产，不能只建少数分析成品模型。
- 语义模型既可以映射单个数据资产，也可以映射多个数据资产的 join、汇总或桥接结果。
- 企业名称到 `taxpayer_id` 的解析属于实体语义能力，应该内建在语义层，不应该默认暴露成用户可见的 SQL 计划节点。
- Planner 和 Executor 应围绕语义模型规划与执行，物理表、原始 SQL 和临时 join 只作为兜底机制。

### 分层关系
1. **数据资产层 (Data Assets)**: PostgreSQL 物理表、治理后的事实表、维度表、分析宽表。
2. **实体与维度层 (Entity/Dimension Semantics)**: 企业、税种、行业、主管税务机关、期间等统一业务主数据与解析规则。
3. **原子事实语义层 (Atomic Fact Semantics)**: 对单个核心数据资产进行口径建模，明确主粒度、实体键、时间键、指标与维度。
4. **复合分析语义层 (Composite Analysis Semantics)**: 在原子事实与维度语义之上形成 join、桥接、偏离、预警、对账等主题模型。
5. **Agent 消费层 (Agent Consumption)**: Understanding、Planner、Executor、Reviewer 围绕语义模型目录、实体解析和证据要求协作。

### 设计原则
- **资产先行**: 每个治理后的核心物理资产，至少应先拥有一个原子语义模型。
- **实体下沉**: 企业、税种、期间等解析与映射沉入语义层，不以显式 SQL 节点形式暴露给用户。
- **复合后置**: 对账、风险画像、税负偏离等复合分析模型建立在原子语义模型之上，而不是替代原子语义模型。
- **语义优先**: 业务问题默认先绑定语义模型，再决定是否需要下探到原始 SQL。
- **证据闭环**: 每个复合分析模型都要声明依赖的原子事实、维度来源和结论证据要求。

### 当前项目的数据资产到语义模型映射建议

| 数据资产层 | 当前物理表/资产 | 建议语义模型类型 | 建议模型名 |
|---|---|---|---|
| 实体维度 | `enterprise_info` | 实体语义模型 | `dim_enterprise` |
| 实体维度 | `dict_industry` | 维度语义模型 | `dim_industry` |
| 实体维度 | `dict_tax_type` | 维度语义模型 | `dim_tax_type` |
| 原子事实 | `tax_vat_declaration` | 原子事实语义模型 | `fact_vat_declaration` |
| 原子事实 | `tax_vat_invoice_summary` | 原子事实语义模型 | `fact_vat_invoice_summary` |
| 原子事实 | `tax_cit_quarterly` | 原子事实语义模型 | `fact_cit_quarterly` |
| 原子事实 | `tax_cit_annual` | 原子事实语义模型 | `fact_cit_annual` |
| 原子事实 | `tax_cit_adjustment_items` | 原子事实语义模型 | `fact_cit_adjustment_item` |
| 原子事实 | `tax_other_taxes` | 原子事实语义模型 | `fact_other_tax_declaration` |
| 原子事实 | `tax_risk_indicators` | 原子事实语义模型 | `fact_tax_risk_indicator` |
| 复合分析 | `recon_revenue_comparison` | 复合分析语义模型 | `mart_revenue_reconciliation` |
| 复合分析 | `recon_tax_burden_analysis` | 复合分析语义模型 | `mart_tax_burden_analysis` |
| 复合分析 | `recon_adjustment_tracking` | 复合分析语义模型 | `mart_adjustment_tracking` |
| 复合分析 | `recon_cross_check_result` | 复合分析语义模型 | `mart_cross_check_result` |

### 当前实现存在的偏差
- 当前仓库中的语义模型仍偏少，且主要集中在少量分析成品模型，不能代表完整语义层。
- 当前 `semantic_query` 编译器基本仍是“单表 metrics/dimensions 编译器”，不足以表达跨资产 join 语义。
- 当前对企业解析仍偏向在运行计划中显式生成 `enterprise_info -> taxpayer_id` 查询步骤，这不符合“实体解析下沉到语义层”的目标。
- 当前计划虽然已经可以携带 `semantic_binding`，但尚未保证每个业务问题都先经过“语义绑定”再执行。

### 语义模型分类定义

#### 1. 实体与维度语义模型
- 负责统一实体主键、显示名、别名、主数据映射、时间维、组织维和行业维。
- 典型能力：`enterprise_name -> taxpayer_id`、行业代码到行业名称映射、税种标准名称归一。
- 这类模型的职责是“解析与约束”，不是直接回答复杂分析结论。

#### 2. 原子事实语义模型
- 一张核心事实表对应一个原子语义模型。
- 明确该事实的主粒度、核心实体键、时间键、基础指标、可过滤维度、默认口径和适用范围。
- 原子语义模型是所有复合分析的证据基础，也是 SQL fallback 的最小受控单元。

#### 3. 复合分析语义模型
- 建立在原子事实模型和维度模型之上。
- 允许多个物理表 join，也允许直接绑定治理后的分析宽表或主题结果表。
- 典型主题：收入对账、税负偏离、风险预警、风险画像、风险成因诊断。
- 每个复合模型都应声明其上游依赖、join 关系、适用场景和证据要求。

### 语义模型注册与表达方式
- `sys_semantic_model` 不应只充当“source_table + yaml_definition”的轻量注册表，而应成为语义目录入口。
- 第一阶段可以继续复用 YAML 作为主配置载体，但 YAML 结构必须升级，至少覆盖：
- `kind`: `entity_dimension | atomic_fact | composite_analysis`
- `domain`: `vat | cit | invoice | risk | reconciliation | burden`
- `grain`: 主粒度
- `sources`: 参与的物理表或上游语义模型
- `joins`: join 路径与键
- `entities`: 主实体、解析器、显示名、过滤映射
- `time`: 默认时间字段、支持粒度、期间展开规则
- `dimensions`: 维度、别名、展示标签、可过滤性
- `metrics`: 基础指标、派生指标、聚合方式、口径说明
- `business_terms`: 业务术语、同义词、典型问法
- `analysis_patterns`: 支持的分析任务，如 `lookup / comparison / warning / diagnosis`
- `evidence_requirements`: 回答结论前必须获取的证据
- `fallback_policy`: 无法直接回答时应回落到哪些原子模型或 SQL

### 语义模型 YAML v2 示例

```yaml
name: mart_tax_risk_alert
label: 税务风险指标预警
kind: composite_analysis
domain: risk
description: 面向企业风险预警查看与高风险指标汇总
grain: indicator_period_enterprise
sources:
  - table: tax_risk_indicators
    alias: risk
  - model: dim_enterprise
    alias: ent
joins:
  - left: risk.taxpayer_id
    right: ent.taxpayer_id
    type: left
entities:
  enterprise:
    primary_key: taxpayer_id
    display_field: enterprise_name
    resolver:
      model: dim_enterprise
      input_fields: [enterprise_name, taxpayer_id]
      output_field: taxpayer_id
time:
  default_field: risk.tax_period
  supported_grains: [month, quarter, year]
dimensions:
  - name: enterprise_name
    expr: ent.enterprise_name
  - name: tax_period
    expr: risk.tax_period
  - name: indicator_name
    expr: risk.indicator_name
  - name: risk_level
    expr: risk.risk_level
metrics:
  - name: indicator_value
    expr: risk.indicator_value
  - name: threshold_value
    expr: risk.threshold_value
  - name: warning_count
    expr: COUNT(*)
business_terms:
  - 税务风险
  - 风险预警
  - 风险指标
analysis_patterns:
  - lookup
  - warning
  - diagnosis
evidence_requirements:
  - 风险指标值
  - 阈值
  - 风险等级
  - 预警说明
fallback_policy:
  prefer_models: [mart_tax_risk_alert, fact_tax_risk_indicator]
  allow_sql: true
```

### Agent 与语义层的关系

#### 1. Semantic Asset Retrieval
- 输入：用户问题、对话历史。
- 输出：候选实体模型、候选原子事实模型、候选复合分析模型、可用实体解析器、相关时间粒度。
- 要求：召回必须先区分“实体模型”“原子模型”“复合模型”，而不是把所有语义模型混成一个扁平候选列表。

#### 2. Understanding Agent
- 输入：用户问题、历史上下文、候选语义资产。
- 输出：结构化 `understanding_result`。
- 要求：理解层回答“用户要看什么业务对象、证据需要什么、优先走哪个主题语义模型”，而不是直接猜 SQL。

#### 3. Grounding Validator
- 输入：`understanding_result`、语义目录、实体解析规则、可用 schema。
- 输出：可执行的语义绑定结果、风险提示、缺失资产说明。
- 要求：如果找不到对应语义模型，应明确说明“缺的是哪一类语义资产”，而不是直接退化成纯 SQL 路径。

#### 4. Semantic-aware Planner
- 输入：用户问题、`understanding_result`、grounding 结果。
- 输出：带 `semantic_binding` 的 `plan_graph`。
- 要求：业务问题的主节点应描述“绑定哪个语义模型并查询什么证据”，而不是优先描述“去哪张表查哪个键”。

#### 5. Semantic-first Executor
- 输入：plan node、`semantic_binding`、历史结果、grounding 结果。
- 输出：语义查询结果、必要的穿透明细、校验结果。
- 要求：实体解析优先通过实体语义模型或内建 resolver 完成；仅当语义层无法承载时才回退到显式 SQL。

#### 6. Reviewer
- 输入：节点结果、最终候选答案、语义绑定信息。
- 输出：`approve / reject / replan`。
- 要求：重点审查口径一致性、实体过滤是否正确、证据是否覆盖结论，而不只审查结果是否“看起来合理”。

### 执行层与 SQL 的关系
- 语义优先不等于“不执行 SQL”，而是“不让 SQL 成为业务理解和规划的主载体”。
- Planner 阶段主要产出 `semantic_binding`，描述“绑定哪个语义模型、查询哪些维度与指标、需要哪些实体过滤”。
- Executor 阶段优先调用 `semantic_query`，由语义编译器根据语义模型动态生成 SQL，再去数据库取数。
- 当语义模型暂时无法表达某个场景时，Executor 才回退到 `sql_executor` 直接执行显式 SQL。
- 因此，执行层最终通常仍会落到 SQL，只是 SQL 的来源应是“语义绑定 -> 语义编译 -> SQL”，而不是“用户问题 -> 直接拼 SQL”。
- 推荐执行链路：

```
用户问题
  → understanding_result
  → semantic_binding
  → semantic_query / semantic compiler
  → compiled SQL
  → database result
  → reviewer
```

### UnderstandingResult 契约

`Understanding Agent` 的输出应从“候选模型列表”升级为“语义层分层绑定建议”，示例如下：

```json
{
  "query_mode": "fact_query|analysis|reconciliation|diagnosis",
  "intent_summary": "查看链龙商贸当前税务风险指标预警",
  "business_goal": "定位企业税务风险预警指标及高风险项",
  "entities": {
    "enterprise_names": ["链龙商贸"],
    "taxpayer_ids": [],
    "periods": [],
    "tax_types": []
  },
  "semantic_scope": {
    "entity_models": ["dim_enterprise"],
    "atomic_models": ["fact_tax_risk_indicator"],
    "composite_models": ["mart_tax_risk_alert"]
  },
  "dimensions": ["enterprise_name", "tax_period", "indicator_name", "risk_level"],
  "metrics": ["indicator_value", "threshold_value", "warning_count"],
  "required_evidence": [
    "风险指标值",
    "阈值",
    "风险等级",
    "预警说明"
  ],
  "resolution_requirements": [
    "将 enterprise_name 解析为 taxpayer_id"
  ],
  "ambiguities": [],
  "confidence": "high"
}
```

#### UnderstandingResult 字段说明

| 字段 | 类型 | 中文含义 |
|---|---|---|
| `query_mode` | string | 当前问题的大类，如事实查询、分析、对账、诊断。 |
| `intent_summary` | string | 用一句话概括系统理解到的真实业务意图。 |
| `business_goal` | string | 本轮真正要回答的业务目标或要解决的问题。 |
| `entities` | object | 从问题中识别出的业务实体集合。 |
| `semantic_scope` | object | 该问题建议绑定的语义模型范围，按实体、原子事实、复合分析分层组织。 |
| `dimensions` | string[] | 本轮问题涉及的分析维度或结果展示维度。 |
| `metrics` | string[] | 本轮问题涉及的指标、数值字段或派生统计项。 |
| `required_evidence` | string[] | 回答结论前必须拿到的证据清单。 |
| `resolution_requirements` | string[] | 执行前必须完成的解析动作要求，例如企业名称转纳税人识别号。 |
| `ambiguities` | string[] | 当前仍存在的歧义、缺失上下文或待确认点。 |
| `confidence` | string | 理解层对本次结构化结果的置信度。 |

#### `entities` 子字段说明

| 字段 | 类型 | 中文含义 |
|---|---|---|
| `enterprise_names` | string[] | 识别出的企业名称或企业简称。 |
| `taxpayer_ids` | string[] | 直接从问题中识别出的纳税人识别号。 |
| `periods` | string[] | 识别出的期间、月份、季度或年度。 |
| `tax_types` | string[] | 识别出的税种，如增值税、企业所得税等。 |

#### `semantic_scope` 子字段说明

| 字段 | 类型 | 中文含义 |
|---|---|---|
| `entity_models` | string[] | 需要参与本轮解析或过滤的实体/维度语义模型。 |
| `atomic_models` | string[] | 作为证据基础的原子事实语义模型。 |
| `composite_models` | string[] | 优先用于回答本轮问题的复合分析语义模型。 |

### Plan 节点升级方向：引入语义绑定而不是显式主数据 SQL

`plan_graph.nodes[]` 的重点不是把实体解析暴露成主任务节点，而是声明本节点如何绑定语义模型、实体和证据：

```json
{
  "id": "n1",
  "title": "查询企业税务风险指标预警",
  "kind": "query",
  "tool_hints": ["semantic_query", "sql_executor"],
  "semantic_binding": {
    "entry_model": "mart_tax_risk_alert",
    "supporting_models": ["dim_enterprise", "fact_tax_risk_indicator"],
    "dimensions": ["enterprise_name", "tax_period", "indicator_name", "risk_level"],
    "metrics": ["indicator_value", "threshold_value", "warning_count"],
    "entity_filters": {
      "enterprise_name": ["链龙商贸"]
    },
    "resolved_filters": {
      "taxpayer_id": []
    },
    "grain": "month",
    "fallback_policy": "atomic_then_sql"
  }
}
```

该设计的含义：
- 用户可见计划重点展示“本轮绑定了哪些语义模型”，而不是先展示一条企业匹配 SQL。
- `entity_filters` 是业务输入，`resolved_filters` 是语义层内部解析后的执行过滤条件。
- 若 `mart_tax_risk_alert` 不存在，可自动退到 `fact_tax_risk_indicator + dim_enterprise` 的组合执行，而不是直接裸查表。

#### Plan Node 顶层字段说明

| 字段 | 类型 | 中文含义 |
|---|---|---|
| `id` | string | 计划节点的唯一标识，用于 DAG 执行和状态跟踪。 |
| `title` | string | 节点的人类可读标题，给用户和调试者看。 |
| `kind` | string | 节点类型，如查询、分析、汇总、可视化等。 |
| `tool_hints` | string[] | 对执行层的工具偏好提示，不是强制执行结果。 |
| `semantic_binding` | object | 本节点绑定的语义模型、过滤条件、指标和执行策略，是执行层的核心契约。 |

#### `semantic_binding` 字段说明

| 字段 | 类型 | 中文含义 |
|---|---|---|
| `entry_model` | string | 本节点首选进入的主语义模型，也就是本轮查询优先从哪个主题模型执行。 |
| `supporting_models` | string[] | 为主模型提供实体解析、补充事实、交叉校验或回退支撑的辅助语义模型。 |
| `dimensions` | string[] | 通过语义层请求返回或聚合时使用的维度。 |
| `metrics` | string[] | 通过语义层请求返回的指标、数值项或统计项。 |
| `entity_filters` | object | 用户问题直接表达出来的业务过滤条件，仍保持业务语义，如企业名称。 |
| `resolved_filters` | object | 经过实体解析、标准化或映射后得到的执行过滤条件，通常更贴近数据库键值，如 `taxpayer_id`。 |
| `grain` | string | 本节点期望的时间或事实粒度，如月、季、年、指标粒度。 |
| `fallback_policy` | string | 当主模型无法直接回答时，执行层应该如何回退，例如先退到原子事实模型，再退到 SQL。 |

#### `entity_filters` / `resolved_filters` 对象说明

| 字段 | 类型 | 中文含义 |
|---|---|---|
| `entity_filters.enterprise_name` | string[] | 用户直接提出的企业名称过滤条件，仍是业务语义表达。 |
| `resolved_filters.taxpayer_id` | string[] | 经过实体解析后用于实际执行的纳税人识别号过滤条件。 |

#### `semantic_binding` 里最容易混淆的字段

| 字段 | 容易混淆点 | 正确认知 |
|---|---|---|
| `entry_model` | 容易被理解成“唯一会用到的模型” | 它是主入口模型，不代表执行时只能用这一个模型。 |
| `supporting_models` | 容易被理解成“可有可无的备注” | 它表示执行时允许依赖的辅助语义模型，常用于实体解析、补证据、做校验。 |
| `entity_filters` | 容易被理解成已经能直接下库查询 | 它是业务输入表达，还没经过实体解析或标准化。 |
| `resolved_filters` | 容易被理解成用户原始输入 | 它是语义层内部解析后的执行条件，通常更接近真实数据库过滤键。 |
| `tool_hints` | 容易被理解成 Executor 必须照做 | 它只是工具偏好，真正执行仍由语义绑定、节点类型和校验规则共同决定。 |

### 问题示例：为什么“查看链龙商贸的税务风险指标预警”不应先出现企业匹配 SQL
- 该问题的主语义主题是“风险预警”，主事实资产是 `tax_risk_indicators`，而不是 `enterprise_info`。
- `enterprise_info` 在这里是实体解析依赖，不应成为用户视角的主任务。
- 正确的语义链路应是：
- 绑定 `dim_enterprise`
- 绑定 `fact_tax_risk_indicator` 或 `mart_tax_risk_alert`
- 在语义层内部完成 `enterprise_name -> taxpayer_id`
- 返回风险指标、阈值、等级、预警说明

### 2026-03-30 设计升级：大模型智能理解层 + 语义模型中心化

### 升级目标
1. 将当前规则型 `runtime_context` 升级为“LLM 理解 + 语义 grounding + 规则校验”的混合智能理解层。
2. 让语义模型从“可选查询工具”升级为“规划与执行的主锚点”。
3. 让 Planner 规划的是“业务语义任务”，而不是“物理表动作序列”。
4. 让 Executor 默认走 `semantic_query`，仅在语义模型无法表达、需要明细穿透或做事实校验时回退到 `sql_executor`。
5. 把实体解析、口径校验、证据要求纳入语义层契约，而不是散落在 prompt 或运行时 SQL 拼接里。

### 升级后的目标链路

```
用户问题
  → Semantic Asset Retrieval（按实体/原子/复合三个层次召回语义资产）
  → Understanding Agent（大模型生成结构化业务理解）
  → Grounding Validator（校验理解结果能否落到真实语义资产）
  → Semantic-aware Planner（生成带语义绑定的 plan_graph）
  → Semantic-first Executor（优先语义查询，必要时原子事实穿透或 SQL 校验）
  → Reviewer（审查实体过滤、口径一致性与证据闭环）
```

### 第一阶段落地边界

为控制改造风险，第一阶段先完成“架构对齐”和“风险主题打通”：

1. 保留已接入的 `understanding_agent.py` 与 `semantic_binding` 骨架。
2. 将 `runtime_context.py` 从“规则猜测器”收缩为“grounding + validator”，弱化其对计划的主导权。
3. 将语义目录按 `entity_dimension / atomic_fact / composite_analysis` 三类重新组织。
4. 先补齐 `dim_enterprise`、`fact_tax_risk_indicator`、`mart_tax_risk_alert` 这一组风险主题语义模型。
5. 扩展 `semantic_query` 编译器，支持多源 `sources + joins` 和实体解析下沉。
6. 调整 Planner/Executor 校验规则，强制业务问题必须携带 `semantic_binding` 才能通过。
7. 将“企业名称解析 taxpayer_id”改为语义层内部能力，不再默认暴露成用户可见 SQL 节点。

### 非第一阶段目标
- 暂不在第一阶段重写全部前端交互。
- 暂不一次性补齐全域所有语义模型，但必须先完成风险主题的标准样板。
- 暂不在第一阶段废除 `sql_executor`，但明确其降级为 fallback。
- 暂不在第一阶段追求所有复杂指标自动派生，先把实体、原子事实和复合主题三层打通。

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
