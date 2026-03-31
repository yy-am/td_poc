# Phase 1：TDA-MQL 语义底座

## 1. 范围

本阶段只做语义底座，不碰多智能体主编排。

包含：

1. `TDA-MQL` 请求协议
2. `TDA-MQL -> semantic_query` 编译入口
3. 语义资产目录增强
4. 税务对账领域资产扩展
5. 最小测试与验证样例

不包含：

1. StageGraph 改造
2. 人工审核断点
3. 真正的 RAG 检索增强
4. 自动归因执行
5. Python 分析执行链

## 2. 实现原则

1. Phase 1 只支持“直接语义取数”这条主线
2. 对暂不支持的 `compare / attribution / advanced drilldown` 明确报错
3. 不写隐式 fallback，不偷偷回退到原始 SQL

## 3. TDA-MQL 最小协议

```json
{
  "header": {
    "reasoning": "用户想看企业 2024Q3 收入对账差异"
  },
  "model_name": "mart_revenue_reconciliation",
  "select": [
    { "metric": "vat_vs_acct_diff", "alias": "revenue_gap" }
  ],
  "group_by": ["enterprise_name", "period"],
  "entity_filters": {
    "enterprise": ["华兴科技有限公司"]
  },
  "filters": [],
  "time_context": {
    "grain": "month",
    "range": "2024Q3"
  },
  "order": [
    { "field": "period", "direction": "asc" }
  ],
  "limit": 100
}
```

## 4. Phase 1 支持能力

### 4.1 支持

- 指定 `model_name`
- 指标选择
- 维度分组
- 实体过滤
- 常规过滤
- 时间范围过滤
- 排序
- 行数限制
- 基于模型 `detail_fields` 的最小下钻

### 4.2 暂不支持

- `time_context.compare`
- 自动归因执行
- 多模型自动拼接
- 自由路径寻径后的自动跨模型编译
- 隐式 SQL fallback

## 5. 语义资产增强字段

本阶段语义目录新增输出：

1. `relationship_graph`
2. `metric_lineage`
3. `detail_fields`
4. `materialization_policy`
5. `query_hints`

## 6. 税务对账资产扩展方向

优先补齐这些验证用资产：

1. 收入对账主题
2. 税负偏离主题
3. 纳税调整追踪主题
4. 风险预警主题
5. 税额滚动与应交税费主题
6. 发票与申报一致性主题
7. 所得税桥接与利润桥主题

### 6.1 本轮已落地的新增主题资产

1. `mart_cit_settlement_bridge`
   - 面向所得税汇算清缴桥接
   - 覆盖会计利润、纳税调整、应纳税所得额、预缴税额、应补退税额
2. `mart_vat_declaration_diagnostics`
   - 面向增值税申报诊断
   - 覆盖销项、进项、转出、应纳税额、有效税负率、免税销售占比
3. `mart_depreciation_timing_difference`
   - 面向折旧税会差异
   - 覆盖会计折旧、税法折旧、月差异、资产级下钻

### 6.2 本轮主链路补强

1. Planner 在命中 `recommended_tool=mql_query` 的复合语义资产时，显式产出：
   - `tool_hints=["mql_query"]`
   - `semantic_binding.query_language="tda_mql"`
   - 推断出的 `time_context`
2. 这个补强是显式契约，不是兜底逻辑
3. 不支持的能力仍然明确报错，不做隐式 SQL 降级

## 7. 验证问题集

Phase 1 至少能稳定支撑以下问题：

1. `分析华兴科技 2024Q3 增值税申报收入与账面收入差异`
2. `查看 2024 年各企业增值税税负率与行业均值偏离`
3. `哪几家企业当前风险等级最高，阈值差多少`
4. `查看华兴科技 2024 年纳税调整项目及递延税影响`
5. `按月份看 2024 年企业所得税利润总额与净利润变化`
6. `查看华兴科技 2024 年所得税汇算清缴桥接，重点看应纳税所得额和应补退税额`
7. `查看华兴科技 2024Q3 增值税申报诊断，分析进项、销项和转出对税负的影响`
8. `查看华兴科技固定资产折旧税会差异，定位差异最大的资产类别`

## 8. 本轮代码完成标准

1. 能通过 API 接收 `TDA-MQL`
2. 能明确告诉调用方哪些能力支持、哪些不支持
3. 能把支持的 `TDA-MQL` 编译成现有 `semantic_query` 请求
4. 语义目录能暴露新增资产字段
5. 税务对账场景的语义资产数量和指标覆盖度明显增加

## 9. 下一批优先企业场景：出口退税对账

为让语义资产更接近企业真实业务，下一批优先补强的不是再堆月度结果表，而是出口退税场景下的单证链对账。

设计结论是：

1. 主对账不应只依赖 `recon_revenue_comparison`
2. 需要三张核心事实表：
- `fact_export_book_revenue_line`
- `fact_export_refund_tax_basis_line`
- `fact_export_contract_discount_line`
3. 其中折扣事实表必须成为一等公民，否则无法解释合同折扣导致的账面 / 税基差异

专项设计见：

- [EXPORT_REBATE_RECONCILIATION_V1.md](/D:/lsy_projects/tda_tdp_poc/design/EXPORT_REBATE_RECONCILIATION_V1.md)

这项工作当前状态是“设计已完成，代码尚未实现”。
