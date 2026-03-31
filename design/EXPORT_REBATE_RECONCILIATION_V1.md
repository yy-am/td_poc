# 出口退税账面收入与税基金额对账语义设计 v1

更新时间：2026-03-31

## 1. 这版设计要解决什么问题

当前项目里的 `mart_revenue_reconciliation` 和 `mart_adjustment_tracking`，已经能支撑“税务申报收入 vs 账面收入”的演示型问数，但还不够贴近企业真实的出口退税对账场景。

问题主要有四个：

1. 当前主资产以月度结果表为中心
- `recon_revenue_comparison` 本质上是“结果已经算好”的月表，不是企业真实会拿来对账的单据级事实。
- 它能回答“差多少”，但回答不了“差异从哪一张合同、哪一笔折扣、哪一条报关单来的”。

2. 缺少出口退税特有的单证链
- 企业真实场景至少会同时面对：
  - 合同
  - 发票
  - 出口报关单 / 报关单行
  - 会计收入确认
  - 退税申报批次 / 税基金额
- 现有模型没有把这些业务键放到一条可追溯链上。

3. 折扣没有成为一等公民
- 合同折扣、返利、价保、质量扣款、后返折让，往往就是账面收入和退税税基不一致的核心原因。
- 当前只能把它写进 `diff_explanation` 文本，无法结构化对账，也无法做“折扣已传递 / 未传递 / 跨期传递”的分析。

4. 时间语义过于单一
- 出口退税对账至少要区分：
  - `book_period`：账面收入所属会计期间
  - `rebate_period`：退税申报所属期间
  - `export_date`：报关出口日期
  - `discount_effective_date`：折扣生效日期
- 当前只有一个通用 `period`，很容易把跨期差异误判成口径差异。

## 2. 场景定义与对账口径

这版设计面向的问题是：

- 某企业某期间出口退税的账面收入与退税税基金额差多少
- 差异里有多少来自合同折扣
- 折扣是只影响账面、只影响税基，还是跨期传递
- 剩余差异是否来自运保费剔除、汇率、单证未匹配或报关调整

本设计采用以下口径：

1. `book_gross_revenue_amount_cny`
- 会计侧已确认的出口收入毛额

2. `book_discount_amount_cny`
- 合同折扣 / 销售返利 / 红字折让等，对账面收入产生影响的金额

3. `book_comparable_revenue_amount_cny`
- 用于与退税税基比较的账面可比收入
- 计算口径：
  - `book_gross_revenue_amount_cny`
  - `- book_discount_amount_cny`
  - `- book_non_basis_exclusion_amount_cny`

4. `rebate_tax_basis_amount_cny`
- 退税申报或退税测算口径下的税基金额

5. `basis_gap_amount_cny`
- 主对账差异
- 定义为：
  - `book_comparable_revenue_amount_cny - rebate_tax_basis_amount_cny`
- 正数表示账面可比收入高于退税税基
- 负数表示退税税基高于账面可比收入

## 3. 数据资产分层

### 3.1 维度资产

保留现有 `dim_enterprise`，并新增两个更贴近业务的维度：

1. `dim_trade_contract`
- 作用：统一合同、客户、币种、贸易术语、产品线
- 主键：`contract_id`

2. `dim_discount_type`
- 作用：统一折扣类型、是否影响账面、是否影响税基、默认分摊规则
- 主键：`discount_type_code`

### 3.2 三张核心事实表

这次设计的核心不是先做一个新的“差异结果表”，而是先把企业真实会出现的三类底层记录建起来。

#### 1. `fact_export_book_revenue_line`

- 角色：账面收入事实
- 粒度：`企业 + 合同行 + 收入确认行 + 会计期间`
- 主用途：提供会计侧收入毛额、非税基口径剔除项、账面可比收入

建议字段：

- 业务键
  - `taxpayer_id`
  - `book_period`
  - `recognition_date`
  - `contract_id`
  - `contract_line_id`
  - `customer_id`
  - `product_id`
  - `shipment_no`
  - `declaration_no`
  - `declaration_line_no`
  - `sales_invoice_no`
  - `voucher_no`
- 金额字段
  - `currency_code`
  - `fx_rate_book`
  - `gross_revenue_amount_doc`
  - `gross_revenue_amount_cny`
  - `freight_amount_cny`
  - `insurance_amount_cny`
  - `commission_amount_cny`
  - `other_non_basis_exclusion_amount_cny`
  - `book_non_basis_exclusion_amount_cny`
  - `book_net_revenue_before_discount_cny`
- 管理字段
  - `source_system`
  - `doc_status`

#### 2. `fact_export_refund_tax_basis_line`

- 角色：退税税基事实
- 粒度：`企业 + 报关单行 / 退税申报行`
- 主用途：提供出口退税口径下可退税税基金额

建议字段：

- 业务键
  - `taxpayer_id`
  - `rebate_period`
  - `export_date`
  - `contract_id`
  - `contract_line_id`
  - `declaration_no`
  - `declaration_line_no`
  - `sales_invoice_no`
  - `customer_id`
  - `product_id`
- 金额字段
  - `currency_code`
  - `fx_rate_customs`
  - `customs_fob_amount_doc`
  - `customs_fob_amount_cny`
  - `rebate_tax_basis_amount_cny`
  - `non_refundable_amount_cny`
  - `rebate_rate`
  - `rebate_tax_amount_cny`
- 管理字段
  - `rebate_batch_no`
  - `source_system`
  - `doc_status`

#### 3. `fact_export_contract_discount_line`

- 角色：合同折扣 / 折让 / 返利事实
- 粒度：`企业 + 折扣单据 + 分摊目标`
- 主用途：把“折扣”从解释文本变成结构化证据

建议字段：

- 业务键
  - `taxpayer_id`
  - `contract_id`
  - `contract_line_id`
  - `discount_doc_no`
  - `discount_type_code`
  - `discount_reason`
  - `book_period`
  - `rebate_period`
  - `effective_date`
  - `related_declaration_no`
  - `related_declaration_line_no`
  - `related_invoice_no`
- 金额字段
  - `currency_code`
  - `fx_rate_discount`
  - `discount_amount_doc`
  - `discount_amount_cny`
  - `book_side_discount_amount_cny`
  - `tax_side_discount_amount_cny`
- 规则字段
  - `affect_book_revenue_flag`
  - `affect_tax_basis_flag`
  - `allocation_method`
  - `allocation_scope`
  - `sync_status`
- 管理字段
  - `source_system`
  - `doc_status`

这张表是本次设计的关键补充。

没有这张表时，系统只能知道“账面收入和税基差了 120 万”，但不知道这 120 万里有多少是：

- 已在账面确认、未传递到税基的合同折扣
- 已经传递到税基、但账面跨期确认的折扣
- 本期签约、下期生效的后返折让

## 4. 关系图与匹配策略

三张事实表不应靠“企业 + 月份”粗暴关联，而应按业务键优先级做匹配。

推荐匹配优先级：

1. `contract_line_id`
2. `declaration_no + declaration_line_no`
3. `sales_invoice_no`
4. `contract_id + product_id + currency_code`
5. `contract_id + product_id + period` 作为最低优先级补充

推荐在语义元数据里显式写出：

- `join_priority`
- `join_confidence`
- `join_fallback_allowed=false`

也就是说：

- 可以有多条候选 Join 路径
- 但不能在运行时偷偷用低置信度路径补出来一个“看起来能算”的结果

## 5. 语义资产设计

### 5.1 原子事实资产

### `fact_export_book_revenue_line`

- `kind`: `atomic_fact`
- `grain`: `enterprise_contract_line_book_period`
- `recommended_tool`: `mql_query`
- 代表指标：
  - `book_gross_revenue_amount_cny`
  - `book_non_basis_exclusion_amount_cny`
  - `book_net_revenue_before_discount_cny`

### `fact_export_refund_tax_basis_line`

- `kind`: `atomic_fact`
- `grain`: `enterprise_declaration_line_rebate_period`
- `recommended_tool`: `mql_query`
- 代表指标：
  - `customs_fob_amount_cny`
  - `rebate_tax_basis_amount_cny`
  - `rebate_tax_amount_cny`
  - `non_refundable_amount_cny`

### `fact_export_contract_discount_line`

- `kind`: `atomic_fact`
- `grain`: `enterprise_discount_doc_allocation_target`
- `recommended_tool`: `mql_query`
- 代表指标：
  - `discount_amount_cny`
  - `book_side_discount_amount_cny`
  - `tax_side_discount_amount_cny`

### 5.2 复合主题资产

### `mart_export_rebate_reconciliation`

- `kind`: `composite_analysis`
- `grain`: `enterprise_contract_line_period`
- 角色：出口退税主对账入口模型

建议维度：

- `enterprise_name`
- `book_period`
- `rebate_period`
- `contract_id`
- `contract_line_id`
- `customer_name`
- `product_name`
- `currency_code`
- `discount_sync_status`
- `match_status`

建议指标：

- `book_gross_revenue_amount_cny`
- `book_non_basis_exclusion_amount_cny`
- `book_discount_amount_cny`
- `book_comparable_revenue_amount_cny`
- `rebate_tax_basis_amount_cny`
- `discount_gap_amount_cny`
- `fx_gap_amount_cny`
- `timing_gap_amount_cny`
- `basis_gap_amount_cny`
- `unresolved_gap_amount_cny`

建议指标口径：

- `book_discount_amount_cny`
  - `SUM(cd.book_side_discount_amount_cny)`
- `book_comparable_revenue_amount_cny`
  - `SUM(br.gross_revenue_amount_cny)`
  - `- SUM(br.book_non_basis_exclusion_amount_cny)`
  - `- SUM(cd.book_side_discount_amount_cny)`
- `discount_gap_amount_cny`
  - `SUM(cd.book_side_discount_amount_cny) - SUM(cd.tax_side_discount_amount_cny)`
- `basis_gap_amount_cny`
  - `book_comparable_revenue_amount_cny - SUM(rb.rebate_tax_basis_amount_cny)`
- `unresolved_gap_amount_cny`
  - `basis_gap_amount_cny`
  - `- discount_gap_amount_cny`
  - `- fx_gap_amount_cny`
  - `- timing_gap_amount_cny`

### `mart_export_discount_bridge`

- `kind`: `composite_analysis`
- `grain`: `enterprise_contract_discount_type_period`
- 角色：专门解释合同折扣如何传递到账面和税基

建议维度：

- `enterprise_name`
- `contract_id`
- `discount_type_name`
- `book_period`
- `rebate_period`
- `sync_status`

建议指标：

- `discount_amount_cny`
- `book_side_discount_amount_cny`
- `tax_side_discount_amount_cny`
- `discount_gap_amount_cny`
- `cross_period_discount_amount_cny`

### `detail_export_rebate_doc_chain`

- `kind`: `detail_object`
- 角色：异常下钻明细对象

建议明细字段：

- `contract_id`
- `contract_line_id`
- `sales_invoice_no`
- `declaration_no`
- `declaration_line_no`
- `voucher_no`
- `discount_doc_no`
- `book_period`
- `rebate_period`
- `gross_revenue_amount_cny`
- `rebate_tax_basis_amount_cny`
- `book_side_discount_amount_cny`
- `tax_side_discount_amount_cny`
- `basis_gap_amount_cny`
- `match_status`
- `discount_sync_status`

### 5.3 为什么不再以 `mart_adjustment_tracking` 作为主入口

现有 `mart_adjustment_tracking` 更像“月度调整汇总主题”，它可以保留，但不适合承接出口退税主对账，原因是：

1. 粒度太粗
- 只有 `企业 + 期间 + 来源类别`

2. 业务键缺失
- 没有合同、报关单行、折扣单据、发票和凭证链路

3. 折扣语义过弱
- 只能说“有折扣类差异”
- 不能说“哪一笔折扣只影响了账面、还没传到税基”

所以它更适合做：

- 月度归类看板
- 高层管理摘要

不适合做：

- 企业级证据链对账入口

### 5.4 一个更贴近项目现状的语义定义示例

```yaml
name: mart_export_rebate_reconciliation
kind: composite_analysis
domain: reconciliation
grain: enterprise_contract_line_period
sources:
  - table: fact_export_book_revenue_line
    alias: br
  - table: fact_export_refund_tax_basis_line
    alias: rb
  - table: fact_export_contract_discount_line
    alias: cd
  - table: enterprise_info
    alias: e
joins:
  - left: br.contract_line_id
    right: rb.contract_line_id
    type: left
    priority: 1
  - left: cd.contract_line_id
    right: br.contract_line_id
    type: left
    priority: 1
  - left: br.taxpayer_id
    right: e.taxpayer_id
    type: left
time:
  primary_role: book_period
  roles:
    book_period:
      field: book_period
      grain: month
    rebate_period:
      field: rebate_period
      grain: month
    export_date:
      field: export_date
      grain: day
    discount_effective_date:
      field: effective_date
      grain: day
query_hints:
  preferred_lane: metric
  supports_drilldown: true
  recommended_patterns:
    - 出口退税对账
    - 合同折扣影响
    - 税基差异诊断
detail_fields:
  - contract_id
  - contract_line_id
  - sales_invoice_no
  - declaration_no
  - discount_doc_no
  - basis_gap_amount_cny
```

## 6. 对 TDA-MQL 的最小增强建议

如果后续要把这个场景真正接进主链，建议只做两项最小增强：

1. `time_context.role`
- 让同一个模型可以明确按 `book_period` 或 `rebate_period` 过滤

2. `semantic_binding.reconcile_key`
- 让 Planner 明确知道这次对账优先按什么业务键聚合
- 例如：
  - `contract_line_id`
  - `declaration_no`
  - `sales_invoice_no`

这两个增强都属于“显式契约增强”，不是隐藏 fallback。

## 7. 这版设计相比当前模型的核心变化

从“按月汇总结果表”切到“按单据链事实表 + 主题桥接模型”。

具体变化是：

1. 差异不再主要放在文本里解释
- 而是拆成结构化的：
  - 折扣差异
  - 跨期差异
  - 汇率差异
  - 运保费剔除
  - 单证未匹配差异

2. 折扣成为第一类事实
- 不再只是 `source_category="合同折扣"` 这种摘要标签

3. 主入口不再是“先算好差异的结果表”
- 而是由账面收入事实、退税税基事实、折扣事实共同生成可追溯主题资产

4. 可以自然支持企业常见问题
- `分析华兴科技 2024Q3 出口退税账面收入与税基差异，重点看合同折扣影响`
- `查看 2024 年哪些合同的折扣只进了账面，尚未传递到退税税基`
- `按报关单下钻差异最大的出口合同`

## 8. 与当前项目的衔接建议

建议按下面顺序推进：

1. 先保留现有 `mart_revenue_reconciliation`
- 继续服务当前收入对账 demo

2. 新增出口退税专项资产
- 先落三张原子事实表
- 再落 `mart_export_rebate_reconciliation`
- 再落 `mart_export_discount_bridge`

3. 再把 Planner 的语义 grounding 补强到这个场景
- 识别“出口退税 / 税基 / 报关单 / 合同折扣 / 返利 / 折让”相关意图词

4. 最后补真实问句回归
- 企业
- 期间
- 合同
- 折扣
- 报关单

## 9. 本轮状态

本轮完成的是“设计定稿”，不是“代码已落地”。

也就是说：

- 已完成：
  - 企业级场景重设计
  - 三张核心事实表定义
  - 语义资产分层设计
  - 折扣桥接口径设计

- 尚未完成：
  - ORM 模型实现
  - Mock 数据生成
  - `semantic_assets.py` 正式接入
  - MQL / Planner / 测试回归

后续如果要真正实现，这份文档应作为出口退税场景的源设计文档，而不是让关键口径继续留在聊天记录里。

## 10. 2026-03-31 实现更新

以下状态覆盖上文“仅完成设计”的旧结论。

### 已完成

- ORM 已落地：
  - `recon_export_book_revenue_line`
  - `recon_export_refund_tax_basis_line`
  - `recon_export_contract_discount_line`
- Mock 数据已落地：
  - 出口账面收入明细
  - 退税税基明细
  - 合同折扣 / 折让 / 返利明细
- 语义资产已落地：
  - `fact_export_book_revenue_line`
  - `fact_export_refund_tax_basis_line`
  - `fact_export_contract_discount_line`
  - `mart_export_rebate_reconciliation`
  - `mart_export_discount_bridge`
- `TDA-MQL` 已支持：
  - `time_context.role=book_period`
  - `time_context.role=rebate_period`
  - `time_context.role=export_date`
  - `time_context.role=discount_effective_date`

### 已验证

- `backend/tests/semantic/test_tda_mql.py`
- `backend/tests/agent/test_semantic_grounding.py`
- `backend/tests/agent/test_executor_agent_v2.py`
- `backend/tests/agent/test_runtime_context.py`
- 结果：`28 passed, 1 warning` + `7 passed`

### 仍然保持的原则

- 不通过写死某个场景 JSON 文件来替代动态分析
- 仍然由前端问句 -> understanding / planner / semantic grounding / MQL 执行主链路来完成分析
- 不引入隐藏 fallback 或隐式 SQL 降级

## 2026-03-31 首跳入口修正

### 修正原因
- 用户指出一个很关键的企业真实场景问题：不会提前把“合同折扣桥接”定义成前端用户首跳进入的主题。
- 更真实的路径应是：
  1. 先做出口退税账面收入 vs 税基金额对账
  2. 再基于差异涉及的公司、期间、合同号继续追问“这些合同是否存在折扣/返利/折让记录”
  3. 如仍需解释折扣在账面与税基间的传递状态，再进入折扣传递支持分析

### 设计调整
- `mart_export_rebate_reconciliation` 明确作为首跳主题，承担“先对账、再定位差异”的入口职责。
- `fact_export_contract_discount_line` 明确承担二跳明细查询职责，支持“是否有折扣单/折扣记录查询/合同有没有折扣”这类追问。
- `mart_export_discount_bridge` 保留，但下调为支持性主题，不再作为默认首跳入口。

### 已落地的技术约束
- `mart_export_discount_bridge.entry_enabled = false`
- semantic grounding 在 `analysis / reconciliation / diagnosis` 场景中，对 `entry_enabled=false` 的主题模型增加降权
- 对账主题增加“差异归因 / 单证链下钻”语义
- 折扣明细主题增加“合同有没有折扣 / 是否有折扣单 / 折扣记录查询”等真实二跳问法

### 当前推荐路径
- 首跳：`分析某公司某期间出口退税账面收入与税基金额差异`
- 二跳：`查看这些差异合同是否有折扣单`
- 三跳（必要时）：`分析这些折扣为何账面已体现但税基未传递`
