# 技术架构设计方案：基于 MQL 语义驱动的智能问数 Agent

## 1. 核心设计哲学 (The "Why")

在开发智能问数系统时，直接让 LLM 生成 SQL（Text-to-SQL）存在三大痛点：

- 幻觉风险：LLM 经常臆造不存在的字段名或 Join 关联键。
- 口径漂移：同一个指标（如“毛利”）在不同 SQL 段落中计算公式不一致。
- 性能黑盒：生成的 SQL 可能产生全表扫描或笛卡尔积。

### 解决方案

引入 MQL（Metrics Query Language）作为中间层，将“业务意图”与“物理实现”解耦。
Agent 负责理解意图并生成 MQL，后端语义引擎负责将 MQL 翻译为高性能、准确的物理 SQL。

## 2. 语义模型元数据设计 (The Foundation)

Codex 需要基于以下元数据结构来理解业务实体。

### 2.1 实体与关联图谱 (Relationship Graph)

是什么：定义表与表之间的拓扑关系。
为什么：当用户问“查看某店长的销售额”时，店长在 `staff` 表，销售额在 `orders` 表。系统需要根据图谱自动找到 `orders -> store -> staff` 的最优 Join 路径。

```jsonc
{
  "entities": [
    { "name": "orders", "type": "fact", "primary_key": "id" },
    { "name": "store", "type": "dimension", "primary_key": "store_id" }
  ],
  "relationships": [
    {
      "source": "orders",
      "target": "store",
      "join_type": "many_to_one",
      "join_on": "orders.store_id = store.store_id",
      "weight": 1 // 权重越小，Join 路径优先级越高
    }
  ]
}
```

### 2.2 指标血缘设计 (Metric Lineage)

是什么：明确指标的计算逻辑及其依赖。
为什么：支持递归查询。如果查询“净利润”，系统需自动拆解为 `(收入 - 成本) * (1 - 税率)`，并分别去底层取数。

- 原子指标（Atomic）：直接映射到物理字段的聚合，如 `SUM(amount)`。
- 复合指标（Composite）：由原子指标通过 SQL 表达式组合而成。

血缘节点结构：

```json
{
  "metric_name": "net_profit",
  "expression": "(${revenue} - ${cost}) * 0.8",
  "depends_on": ["revenue", "cost"],
  "description": "净利润 = (收入 - 成本) * 固定税率0.8"
}
```

## 3. MQL 协议规范 (The Communication)

MQL 是 Agent 的输出物，也是翻译器的输入物。

### 3.1 MQL JSON 示例

```jsonc
{
  "header": { "reasoning": "用户想看华东区近三个月的利润趋势并对比去年" },
  "select": [
    { "metric": "net_profit", "alias": "profit" },
    { "metric": "revenue", "alias": "rev" }
  ],
  "group_by": ["region", "month"],
  "filter": [
    { "dimension": "region", "op": "IN", "values": ["华东", "华南"] }
  ],
  "time_context": {
    "grain": "month",
    "range": "last_3_months",
    "compare": "YoY" // 自动触发同比计算逻辑
  }
}
```

## 4. 智能分析与下钻逻辑 (The Logic)

### 4.1 自动归因算法 (Attribution Analysis)

为什么：当用户问“为什么上月利润下降了？”时，Agent 不能只给一个数字，而要给出原因。

第一步：血缘拆解。检查 `revenue` 和 `cost` 哪个波动更大。
第二步：维度钻取。对波动大的指标，遍历其所有关联维度（如：品类、渠道）。
第三步：贡献度计算。

$$
Contribution_{dim} = \frac{\Delta Value_{dim\_member}}{\Delta Value_{total}}
$$

Codex 应实现一个函数：输入 MQL 结果集，自动返回贡献度前三的维度成员。

### 4.2 细粒度下钻 (Drill-down to Grain)

为什么：用户看总计数据发现异常后，通常会要求“看下具体是哪些订单”。

- 逻辑转换：将 MQL 的 `group_by` 字段替换为该实体的 Primary Key（如 `order_id`）。
- 字段穿透：从语义层的 `Detail_Fields` 列表中提取非聚合字段（如：备注、流水号、操作人）。
