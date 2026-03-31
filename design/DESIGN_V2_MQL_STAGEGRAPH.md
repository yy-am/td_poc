# TDA 语义问数 v2 方案

## 1. 目标

v2 的目标不是继续强化 `Text-to-SQL`，而是建立一套适合税务对账场景的：

- 语义执行层：`NL -> TDA-MQL -> SQL`
- 分析控制层：`StageGraph`
- 证据与解释层：语义资产 + 领域知识

核心原则：

1. 数值结论必须来自受控语义执行，不允许直接依赖 LLM 臆造 SQL。
2. 业务解释、政策口径、案例建议可以由知识层增强，但不能替代取数。
3. 复杂分析必须可暂停、可审核、可追溯。

## 2. 总体架构

```text
用户问题
  -> IntentRecognition
  -> SemanticBinding
  -> TDA-MQL Draft
  -> FeasibilityAssessment
  -> StageGraph Planning
  -> HumanGate
  -> Metric / Detail / Python Execution
  -> EvidenceVerification
  -> ReportGeneration
```

分层职责：

1. 语义执行层
   - 统一实体、维度、指标、明细对象、时间语义、关系图谱、物化策略。
   - 将 `TDA-MQL` 编译为可控 SQL。
2. StageGraph 控制层
   - 管理阶段状态、人工审核、执行顺序、失败中止、证据校验。
3. 领域知识层
   - 提供政策口径、分析 SOP、历史案例、指标释义，不负责最终数字。

## 3. TDA-MQL 定位

`TDA-MQL` 是 Agent 和语义引擎之间的中间协议。

Agent 负责：

- 理解用户意图
- 识别实体、指标、维度、时间范围
- 输出结构化 `TDA-MQL`

语义引擎负责：

- 校验模型、字段、关系、时间语义
- 转译为受控 SQL
- 约束粒度、下钻、成本与权限

这层协议用于消除三个核心风险：

1. 字段幻觉
2. 指标口径漂移
3. SQL 性能不可控

## 4. 语义执行层设计

### 4.1 语义资产类型

v2 不再把语义模型理解成“某张表的 YAML 描述”，而是完整的语义资产目录：

1. `entity_dimension`
   - 企业、行业、税种、科目等主数据与解析规则
2. `atomic_fact`
   - 单一核心事实资产
3. `composite_analysis`
   - 围绕对账、税负偏离、风险、归因的主题模型
4. `detail_object`
   - 用于异常下钻时返回的明细字段集合

### 4.2 一等公民元数据

每个语义资产至少补齐以下字段：

1. `relationship_graph`
   - 数据源之间的关系图谱、Join 方向、Join 键和优先级
2. `metric_lineage`
   - 原子指标、派生指标、复合指标及其依赖图
3. `time`
   - 主时间字段、支持粒度、业务时间角色
4. `detail_fields`
   - 支持下钻时可返回的细粒度字段
5. `materialization_policy`
   - 优先走宽表、事实表还是其它受控资产
6. `query_hints`
   - 推荐入口、成本级别、是否支持下钻、是否适合趋势/比较/诊断

### 4.3 税务对账场景的时间语义

税账场景不能只有一个通用时间字段。

需要显式区分：

- `tax_period`
- `acct_period`
- `invoice_date`
- `declaration_date`
- `tax_year`

`TDA-MQL.time_context` 必须与模型的时间语义对齐，避免税务期间与会计期间混用。

## 5. StageGraph 设计

### 5.1 阶段定义

推荐阶段如下：

1. `IntentRecognition`
2. `SemanticBinding`
3. `TdaMqlDraft`
4. `FeasibilityAssessment`
5. `EvidenceRecall`
6. `Planner`
7. `HumanGate`
8. `MetricExecution`
9. `DetailExecution`
10. `PythonAttribution`
11. `EvidenceVerification`
12. `ReportGeneration`

### 5.2 人工干预原则

人工审核断点应发生在执行前，而不是仅在执行后自审。

以下情形必须进入 `HumanGate`：

- 存在多个候选语义模型
- 存在多条 Join 路径
- 查询成本高
- 涉及敏感数据
- 输出正式报告

## 6. 领域知识层

知识层只做增强，不做取数。

包含三类内容：

1. 指标释义与口径库
2. 政策 / 会计准则 / 税法规则库
3. 分析 SOP / 历史案例库

它的用途是：

- 辅助语义绑定
- 解释异常
- 生成报告与建议

## 7. Phase 规划

### Phase 1：语义底座 v2

范围：

- 建立 `TDA-MQL` 协议
- 扩展语义资产元数据
- 丰富税务对账领域语义资产
- 提供编译与校验接口

当前 Phase 1 的明确落地策略：

- 对命中指标语义强、`recommended_tool=mql_query` 的复合分析资产，Planner 必须显式走 `TDA-MQL` 主路径
- 代表性税务对账资产优先覆盖：收入错期、税负偏离、应交税费滚动、所得税汇缴桥接、折旧税会差异
- 未支持的 compare / attribution / Python 诊断仍明确报错，不做隐式降级

### Phase 2：StageGraph v1

范围：

- 将现有多智能体执行链升级为显式阶段流
- 加入人工审核断点
- 前端展示阶段状态而不只是执行 DAG

### Phase 3：归因、下钻、报告

范围：

- 自动归因
- 明细下钻
- 独立报告节点

### Phase 4：知识治理与性能

范围：

- RAG 检索治理
- 权限、审计、血缘
- 物化与缓存

## 8. 实施约束

本轮实现遵守以下约束：

1. 不额外编写用户未要求的 fallback 逻辑
2. 当前不改 orchestrator 主链，只搭语义底座
3. 对未支持的 MQL 能力，返回明确校验错误，不做偷偷降级

## 9. 2026-03-30 落地补充

### 已完成

- `StageGraph v0` 已接入当前主链：
  - 新增 `backend/app/agent/stage_graph.py`
  - `backend/app/agent/orchestrator.py` 已显式发出 `stage_update`
  - 当前阶段顺序为：
    - `intent_recognition`
    - `semantic_binding`
    - `planning`
    - `execution`
    - `review`
    - `report_generation`
- 前端已可消费阶段图：
  - `frontend/src/types/agent.ts` 新增 `stage_update / stage_graph / stage_id / stage_status`
  - `frontend/src/components/chat/MultiAgentBoardClean.vue` 会在真实 LLM `plan_graph` 出现前先显示 `StageGraph v0`
  - 选中阶段事件时，右侧图会切换到对应阶段快照

### 已验证

- 后端测试：`37 passed`
- 前端构建：`npm run build` 通过
- 新增 `backend/tests/agent/test_orchestrator.py`
  - 验证主链路会按顺序发出阶段事件
  - 验证最终答案前会完整走到 `report_generation`

### 仍保持的约束

- 不新增隐式 SQL fallback
- `tda_mql` 对未支持能力继续显式报错
- 当前 `StageGraph v0` 只做可见性与显式状态流，不引入人工审核暂停/恢复

## 10. 2026-03-30 前端视图对齐补充

- 中间图主组件已切换为 `frontend/src/components/chat/PlanFlowDeckClean.vue`
- 当前前端优先展示 `StageGraph v0` 的 6 段阶段流：
  - `intent_recognition`
  - `semantic_binding`
  - `planning`
  - `execution`
  - `review`
  - `report_generation`
- 真实 LLM `plan_graph` 到达后，仍保留卡片化计划图展示，不覆盖现有 agentic 计划能力
- 参考样式文件 `design/agent-visual-prototypes/v7-right-inspector-bilingual.html` 已改成 StageGraph 语义，不再沿用旧的 “Evidence Execution / Delivery” 语言
- 这次调整只做展示层对齐，不新增任何隐式 fallback 或额外执行兜底

## 11. 2026-03-31 P0/P1 Implementation Notes

### Landed now

- `TDA-MQL` Phase 1 now supports explicit compare execution for:
  - `yoy`
  - `mom`
  - `qoq`
  - `previous_period`
- Compare is implemented as controlled dual semantic execution plus merge, not as hidden SQL fallback.
- Drill-down remains controlled by declared `detail_fields`.
- `compare + drilldown` is still intentionally blocked in Phase 1.
- `analysis_mode.attribution` and diagnosis-style flows are still intentionally blocked in Phase 1.

### StageGraph now in runtime

- Runtime stage model has been upgraded to `StageGraph v1-lite` with these stages:
  - `intent_recognition`
  - `semantic_binding`
  - `tda_mql_draft`
  - `feasibility_assessment`
  - `planning`
  - `metric_execution`
  - `detail_execution`
  - `evidence_verification`
  - `review`
  - `report_generation`
- This is still a non-HITL runtime graph:
  - no human gate
  - no pause/resume
  - no stage persistence yet

### Still deferred on purpose

- Human intervention checkpoints
- Multi-turn conversation governance
- Python attribution branch
- Knowledge-layer recall injected into the stage runtime

## 12. 企业真实场景补强：出口退税账面收入 vs 税基金额对账

当前 `mart_revenue_reconciliation` 更适合“月度税会收入差异”的通用场景，但还不够贴近企业真实的出口退税对账。

针对这个场景，v2 需要把主数据资产从“结果表导向”进一步推进到“单证链事实导向”：

1. `fact_export_book_revenue_line`
- 账面收入事实

2. `fact_export_refund_tax_basis_line`
- 退税税基事实

3. `fact_export_contract_discount_line`
- 合同折扣 / 折让 / 返利事实

这第三张折扣事实表是关键补充。

如果没有它，系统最多只能回答“账面收入与税基差多少”，但无法结构化回答：

- 哪些差异是合同折扣导致
- 折扣是只影响账面、只影响税基，还是跨期传递
- 哪些合同折扣已经进入税基，哪些还停留在账面

对应的专项设计文档见：

- [EXPORT_REBATE_RECONCILIATION_V1.md](/D:/lsy_projects/tda_tdp_poc/design/EXPORT_REBATE_RECONCILIATION_V1.md)

本次设计同时明确：

- 出口退税对账至少需要区分 `book_period / rebate_period / export_date / discount_effective_date`
- 不能再只依赖单一 `period`
- 主对账资产应升级为 `mart_export_rebate_reconciliation`
- `mart_adjustment_tracking` 适合作为摘要主题，不适合作为企业级证据链主入口

## 2026-03-31 出口退税入口主题修正
- 出口退税场景的首跳主题应为 `mart_export_rebate_reconciliation`，负责“账面收入 vs 税基金额”的先对账再归因。
- `mart_export_discount_bridge` 不再视为默认入口主题，而是对账后的支持性二跳分析主题。
- 用户追问“这些合同是否有折扣/返利/折让记录”时，优先落到 `fact_export_contract_discount_line`，而不是直接进入折扣桥接主题。
