# TDA v2 项目进展

## 2026-03-31 Agent Flow / Validation Update

### 新增根目录文档

- 已新增 `AGENT_FLOW_CURRENT.md`
- 这份文档沉淀了：
  - 当前真实阶段表
  - 当前真实时序图
  - 大模型调用次数分析
  - 当前方案优点、不足与改进方向

### 本轮已落地的两个改进点

- `TDA-MQL` 草拟阶段不再只是展示草稿
  - orchestrator 会先做 `TdaMqlRequest` 校验
  - 再做正式语义编译校验
  - 草稿不合法会直接阻断在 `tda_mql_draft`
- 审查 / 汇总阶段不再隐式兜底
  - 审查 JSON 非法时不再默认通过
  - 审查异常时不再默认通过
  - 报告生成异常时不再自动拼 fallback answer
  - `report_generation` 会显式 blocked 并输出错误事件

### 本轮未做的第三点

- 审查成本优化还没做
- 下一步建议是：
  - 规则先审
  - 模型补审

### 本轮验证

- 新增 `backend/tests/agent/test_reviewer_agent_v2.py`
- 扩展 `backend/tests/agent/test_orchestrator.py`
- 更新 `backend/tests/agent/test_stage_graph_v1_lite_spec.py`
- 后端全量测试通过：`57 passed, 1 warning`

更新时间：2026-03-31

这份文件是当前项目的统一进度入口，后续继续 `design_v2` 和项目开发时，优先先看这里。

## 1. 当前目标

项目当前明确朝这条路线推进：

- 语义执行层：`NL -> TDA-MQL -> SQL`
- 分析控制层：`StageGraph`
- 领域知识层：税务/账务/对账知识资产
- 前端工作台：浅色、可读、能看出“模型现在在干什么”

主设计文档是：

- [DESIGN_V2_MQL_STAGEGRAPH.md](/D:/lsy_projects/tda_tdp_poc/design/DESIGN_V2_MQL_STAGEGRAPH.md)
- [PHASE1_TDA_MQL.md](/D:/lsy_projects/tda_tdp_poc/design/PHASE1_TDA_MQL.md)
- [FRONTEND_STAGEGRAPH_REFRESH_V1.md](/D:/lsy_projects/tda_tdp_poc/design/FRONTEND_STAGEGRAPH_REFRESH_V1.md)

## 2. 已完成内容

### 2.1 语义底座 Phase 1

已经落地：

- `TDA-MQL` 基础协议与执行入口
- `mql/validate` 与 `mql/query` API
- 语义资产元数据增强：
  - `relationship_graph`
  - `metric_lineage`
  - `detail_fields`
  - `materialization_policy`
  - `query_hints`
- Planner 命中复合语义资产时，会显式优先走 `mql_query`

相关核心文件：

- [mql.py](/D:/lsy_projects/tda_tdp_poc/backend/app/semantic/mql.py)
- [semantic_v2.py](/D:/lsy_projects/tda_tdp_poc/backend/app/api/semantic_v2.py)
- [semantic_assets.py](/D:/lsy_projects/tda_tdp_poc/backend/app/mock/semantic_assets.py)
- [planner_agent_v2.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/planner_agent_v2.py)
- [planner_prompt_v3.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/prompts/planner_prompt_v3.py)

### 2.2 税务对账数据资产

已经持续补了一批用于 case 验证的复合语义资产，方向集中在税务对账高频场景：

- 收入错期
- 增值税税负偏低
- 应交税费滚动
- 企业所得税纳税调整桥接
- 汇算清缴桥接
- 增值税申报诊断
- 折旧税会差

当前判断：语义资产已经不是演示级别的几张表映射，而是开始具备“围绕问题组织资产”的雏形。

### 2.3 企业真实场景设计补强

本轮新增了一份更贴近企业真实业务的专项设计文档：

- [EXPORT_REBATE_RECONCILIATION_V1.md](/D:/lsy_projects/tda_tdp_poc/design/EXPORT_REBATE_RECONCILIATION_V1.md)

这份设计不是再补一个“出口退税差异结果表”，而是把场景重构为三张核心事实表：

- `fact_export_book_revenue_line`
- `fact_export_refund_tax_basis_line`
- `fact_export_contract_discount_line`

关键结论：

- 现有 `mart_revenue_reconciliation` 更像通用月度结果资产，不足以承接出口退税的企业级证据链对账
- 合同折扣必须成为第三张结构化事实表，而不是继续塞进 `diff_explanation`
- 时间语义至少要显式区分 `book_period / rebate_period / export_date / discount_effective_date`

当前状态：

- 设计已完成
- 尚未进入 ORM / mock / semantic asset / 回归测试实现

### 2.4 StageGraph v0

已经落地：

- 后端显式 `StageGraph v0`
- Orchestrator 主链路会发 `stage_update`
- 当前阶段顺序：
  - `intent_recognition`
  - `semantic_binding`
  - `planning`
  - `execution`
  - `review`
  - `report_generation`

相关核心文件：

- [stage_graph.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/stage_graph.py)
- [orchestrator.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/orchestrator.py)
- [agent.ts](/D:/lsy_projects/tda_tdp_poc/frontend/src/types/agent.ts)

### 2.5 前端工作台换代

已经完成一轮主入口级别的前端改造：

- 聊天页整体改成浅色、轻透、清新的工作台风格
- 中间主图不再以线性 stage ribbon 为主视觉
- 新入口组件链路已经接入聊天页：
  - [MultiAgentBoardRefresh.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/MultiAgentBoardRefresh.vue)
  - [NavigatorRail.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/NavigatorRail.vue)
  - [WorkbenchCanvas.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/WorkbenchCanvas.vue)
  - [InsightInspector.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/InsightInspector.vue)
- 聊天页外壳已经切到新视觉：
  - [ChatView.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/views/ChatView.vue)

当前前端结构是：

- 顶部 `Question Ribbon`
- 左侧 `Navigator`
- 中间非线性 `Workbench`
- 右侧 `Inspector`

## 3. 已验证事实

### 3.1 后端与语义链路

已验证过：

- `TDA-MQL` 相关后端测试通过
- Planner 增强后，真实主链路里已经能稳定更高概率先产出 `mql_query`
- 主链路已经能跑到 `Query Revenue Reconciliation -> mql_query`

### 3.2 StageGraph 与前端

已验证过：

- `StageGraph v0` 已经能进入真实链路
- 前端可以消费阶段事件
- 新前端工作台构建通过

已执行的验证类型：

- backend pytest
- frontend `npm run build`
- 真实服务 smoke test
- 真实 WebSocket 主链路观察

## 4. 当前边界与约束

这些是现在必须继续遵守的，不要后续开发时丢掉：

- 不要加用户没要求的兜底逻辑
- 不要做隐式 SQL fallback
- 对未支持能力明确报错，不要偷偷降级
- 当前人工审核断点还没开始做，不要擅自接入
- 当前重点仍然是把 `TDA-MQL + StageGraph + 税务资产` 这条主线做扎实

尤其注意：

- `compare / attribution / Python analysis` 目前仍未完整实现
- `StageGraph v1` 还没开始做暂停/恢复/人工审核
- 旧组件还在仓库里，但聊天主入口已经切到新组件链路

## 5. 当前最真实的项目状态

一句话总结：

现在项目已经从“概念设计期”进入了“v2 主链路成型期”。

更具体一点：

- 语义层已经不再只是想法，`TDA-MQL` 和语义资产增强已经落地
- StageGraph 已经不是文档里的概念，`v0` 已经接到主链路
- 前端也已经不只是设计稿，新的工作台已经接入聊天页
- 但企业级闭环还没完成，尤其是：
  - 人工审核
  - 归因与下钻
  - 报告节点深化
  - 知识层治理

## 6. 下一步建议顺序

后面继续开发时，建议按这个顺序推进：

1. 继续补强 Phase 1
- 继续增加税务对账数据资产
- 优先把出口退税账面收入 vs 税基金额对账场景落到代码
- 继续做真实问句回归
- 稳定 Planner -> `mql_query` 主路径

2. 收紧前端工作台与真实链路的一致性
- 用真实问句观察新工作台
- 调整 Workbench 上下文、焦点、证据信号的展示质量

3. 再进入 StageGraph v1
- 人工审核断点
- 暂停 / 恢复
- 阶段状态更细化

4. 最后推进归因、下钻、报告
- attribution
- detail drill-down
- report generation

## 7. 恢复开发时建议先看

如果后续要继续这条线，建议阅读顺序：

1. [PROJECT_PROGRESS_V2.md](/D:/lsy_projects/tda_tdp_poc/design/PROJECT_PROGRESS_V2.md)
2. [DESIGN_V2_MQL_STAGEGRAPH.md](/D:/lsy_projects/tda_tdp_poc/design/DESIGN_V2_MQL_STAGEGRAPH.md)
3. [PHASE1_TDA_MQL.md](/D:/lsy_projects/tda_tdp_poc/design/PHASE1_TDA_MQL.md)
4. [FRONTEND_STAGEGRAPH_REFRESH_V1.md](/D:/lsy_projects/tda_tdp_poc/design/FRONTEND_STAGEGRAPH_REFRESH_V1.md)

然后再看关键代码：

- [planner_agent_v2.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/planner_agent_v2.py)
- [mql.py](/D:/lsy_projects/tda_tdp_poc/backend/app/semantic/mql.py)
- [stage_graph.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/stage_graph.py)
- [orchestrator.py](/D:/lsy_projects/tda_tdp_poc/backend/app/agent/orchestrator.py)
- [ChatView.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/views/ChatView.vue)
- [MultiAgentBoardRefresh.vue](/D:/lsy_projects/tda_tdp_poc/frontend/src/components/chat/MultiAgentBoardRefresh.vue)

## 8. 本文件用途

后面如果继续推进：

- `DESIGN_V2_MQL_STAGEGRAPH.md` 负责“设计目标和架构原则”
- `PROJECT_PROGRESS_V2.md` 负责“做到哪了、验证到哪了、下一步接什么”

这两个文件配合使用，避免后续恢复时又得重新梳理一次上下文。

## 9. 2026-03-31 P0/P1 Delivery Update

### Delivered in this round

- P0 single-turn main path is now stable under test:
  - planner keeps preferring `mql_query` for the supported tax reconciliation assets
  - backend full test suite passes without adding any hidden fallback path
- P1 semantic execution now covers:
  - `time_context.compare` for `yoy / mom / qoq / previous_period`
  - compare result merge with `compare_* / delta_* / delta_rate_*` columns
  - controlled detail drill-down using declared `detail_fields`
  - explicit rejection for unsupported `compare + drilldown` and `attribution`
- P1 StageGraph is upgraded from `v0` to `v1-lite`:
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
- Frontend workbench is already wired to the newer stage model and compare/drilldown metadata.

### Verification completed

- Backend targeted tests:
  - `backend/tests/semantic/test_tda_mql.py`
  - `backend/tests/agent/test_stage_graph.py`
  - `backend/tests/agent/test_stage_graph_v1_lite_spec.py`
  - `backend/tests/agent/test_orchestrator.py`
- Backend full suite:
  - `43 passed, 1 warning`
- Frontend build:
  - `npm run build` passed
  - first sandbox attempt failed with `spawn EPERM`
  - rerun outside sandbox succeeded, so this was an environment restriction, not an app logic failure

### Constraints still in force

- No hidden fallback logic
- No implicit SQL fallback for the explicit MQL path
- Human gate and multi-turn state are still intentionally deferred
- Unsupported capabilities must fail explicitly instead of degrading silently

### Remaining after P0/P1

- More real tax reconciliation assets and real-query regression coverage
- Knowledge layer / evidence recall
- Report-generation node hardening
- Human review checkpoints
- Multi-turn context governance

### Cleanup status

- Obsolete temporary `.new` files from this round have been deleted.
- Old unused chat workbench files replaced by the refresh workbench have also been removed.

## 2026-03-31 出口退税场景实现完成

### 本轮已落地

- 新增 3 张底层事实表
  - `recon_export_book_revenue_line`
  - `recon_export_refund_tax_basis_line`
  - `recon_export_contract_discount_line`
- mock 数据链路已补齐
  - `backend/app/mock/generator.py` 新增出口退税单证链数据
  - `backend/app/api/mock_data_v2.py` 已纳入新表清理顺序
- 语义资产已落地
  - `fact_export_book_revenue_line`
  - `fact_export_refund_tax_basis_line`
  - `fact_export_contract_discount_line`
  - `mart_export_rebate_reconciliation`
  - `mart_export_discount_bridge`
- `TDA-MQL` 已支持 `time_context.role`
  - 可按 `book_period / rebate_period` 切换过滤
  - 支持 `export_date / discount_effective_date` 这类日期角色按月/季度/年度生成 date range filter

### 验证结果

- 通过：
  - `backend/tests/semantic/test_tda_mql.py`
  - `backend/tests/agent/test_semantic_grounding.py`
  - `backend/tests/agent/test_executor_agent_v2.py`
  - `backend/tests/agent/test_runtime_context.py`
- 实际结果：
  - `28 passed, 1 warning`
  - `7 passed`

### 本轮边界

- 没有改后端 agent 主流程
- 没有引入隐藏 fallback / 隐式 SQL 降级
- 明确不采用“写死某个场景分析 JSON 文件”的方式
- 目标仍然是让用户通过前端提问后，由现有 agent + semantic path 动态完成分析

## 2026-03-31 出口退税入口语义修正
### 本轮新增
- 按用户反馈修正了出口退税场景的入口建模：
  - 首跳入口固定为 `mart_export_rebate_reconciliation`
  - `fact_export_contract_discount_line` 负责二跳“这些合同有没有折扣单/折扣记录”
  - `mart_export_discount_bridge` 下调为支持性主题，不再作为默认首跳入口
- semantic grounding 新增入口偏好规则：分析/对账类问句会优先命中 `entry_enabled=true` 的主题模型

### 已验证
- `backend/tests/agent/test_semantic_grounding.py`
- `backend/tests/semantic/test_tda_mql.py`
- `backend/tests/agent/test_executor_agent_v2.py`
- `backend/tests/agent/test_runtime_context.py`
- 结果：`38 passed, 1 warning`
