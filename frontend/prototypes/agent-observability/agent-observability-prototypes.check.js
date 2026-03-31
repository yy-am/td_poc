
    const variantMeta = {
      v1: {
        title: 'V1 Command Graph / 指挥中枢图',
        subtitle: '以阶段 rail + 发光节点图为主，第一眼就能看到 Understanding、Planner、Executor、Reviewer 的职责和推进状态。'
      },
      v2: {
        title: 'V2 Swimlane Cinema / 执行泳道图',
        subtitle: '以泳道方式强化阶段职责和先后关系，最适合解释“每个阶段到底做了什么”。'
      },
      v3: {
        title: 'V3 Evidence Topology / 证据拓扑图',
        subtitle: '把问题、语义模型、执行工具和证据之间的关系拉成拓扑，更适合强调语义中心化和证据闭环。'
      }
    }

    const nodeData = {
      'semantic-retrieval': {
        title: '语义资产召回',
        meta: ['Understanding', 'active', 'click to inspect'],
        summary: '先按实体模型、原子事实模型、复合主题模型三个层次召回候选资产，避免 Planner 直接从物理表猜起。',
        semantic: ['dim_enterprise', 'fact_tax_risk_indicator', 'mart_tax_risk_alert'],
        tools: ['semantic catalog', 'entity resolver', 'schema grounding'],
        evidence: ['候选实体模型：dim_enterprise', '候选原子模型：fact_tax_risk_indicator', '候选复合模型：mart_tax_risk_alert'],
        sql: `/* no direct SQL here */
SELECT model_name, kind, domain
FROM semantic_catalog
WHERE business_terms ILIKE '%风险预警%'
ORDER BY score DESC;`,
        reasoning: '识别问题主题是“税务风险指标预警”。\n优先命中 risk 域语义模型。\n因为用户输入的是企业名称，必须带入实体解析能力。\n如果只召回 enterprise_info 而不召回 risk facts，后续计划会退化成主数据 SQL。'
      },
      'entity-resolve': {
        title: '实体解析',
        meta: ['Understanding', 'resolver', 'entity'],
        summary: '企业解析在语义层内部完成，不应变成用户可见的主任务节点。这里展示的是 Inspector 中的内部子步骤。',
        semantic: ['dim_enterprise'],
        tools: ['resolver'],
        evidence: ['输入实体：链龙商贸', '输出执行键：taxpayer_id', '保留名称与执行键双轨过滤'],
        sql: 'SELECT taxpayer_id\nFROM enterprise_info\nWHERE enterprise_name = :enterprise_name\nLIMIT 1;',
        reasoning: '这是内部解析步骤。\n应该在 Inspector 可见，但默认不在主图中抢走主题。\n主图应该围绕风险预警主题，而不是围绕企业主数据。'
      },
      'understanding': {
        title: 'Understanding + Grounding',
        meta: ['Planner', 'semantic scope', 'structured intent'],
        summary: '把用户问题转成 structured intent，包括 semantic_scope、required_evidence 和 resolution_requirements。',
        semantic: ['dim_enterprise', 'fact_tax_risk_indicator', 'mart_tax_risk_alert'],
        tools: ['llm understanding', 'grounding validator'],
        evidence: ['intent_summary: 查看链龙商贸当前税务风险指标预警', 'required_evidence: 风险值 / 阈值 / 风险等级 / 预警说明', 'resolution_requirements: enterprise_name -> taxpayer_id'],
        sql: '/* no direct SQL here */\n/* grounding works on semantic scope, schema, and entity rules */',
        reasoning: '本轮问题不是 metadata 问题。\n它不是单纯查企业信息，而是风险主题 fact query。\n主模型应优先是风险预警主题模型，实体解析只是支持动作。'
      },
      'planner-bind': {
        title: 'Plan + Semantic Binding',
        meta: ['Planner', 'plan graph', 'binding'],
        summary: 'Planner 输出的不是“先查哪张表”，而是“本节点绑定哪个主语义模型、哪些 supporting models、哪些过滤条件和证据需求”。',
        semantic: ['mart_tax_risk_alert', 'dim_enterprise', 'fact_tax_risk_indicator'],
        tools: ['planner'],
        evidence: ['entry_model = mart_tax_risk_alert', 'supporting_models = dim_enterprise, fact_tax_risk_indicator', 'entity_filters.enterprise_name = 链龙商贸'],
        sql: '/* plan layer does not emit final SQL */\nsemantic_binding = {\n  entry_model: "mart_tax_risk_alert",\n  supporting_models: ["dim_enterprise", "fact_tax_risk_indicator"]\n}',
        reasoning: '如果 Planner 产出的是 enterprise_info 精确匹配 SQL，说明计划被物理层劫持了。\n正确做法是把 enterprise_name 保留在 entity_filters，把解析后的 taxpayer_id 放进 resolved_filters。'
      },
      'executor-query': {
        title: 'Semantic Query Node',
        meta: ['Executor', 'semantic_query', 'compiled SQL'],
        summary: 'Executor 优先走 semantic_query。真正的 SQL 由语义绑定和语义编译器生成，而不是直接从用户问题硬写出来。',
        semantic: ['mart_tax_risk_alert', 'fact_tax_risk_indicator'],
        tools: ['semantic_query', 'sql compiler'],
        evidence: ['返回字段：indicator_name / indicator_value / threshold_value / risk_level / alert_message', '实体过滤：resolved_filters.taxpayer_id', '保留 SQL preview 以便节点级排错'],
        sql: 'SELECT ent.enterprise_name,\n       risk.tax_period,\n       risk.indicator_name,\n       risk.indicator_value,\n       risk.threshold_value,\n       risk.risk_level,\n       risk.alert_message\nFROM tax_risk_indicators AS risk\nLEFT JOIN enterprise_info AS ent\n  ON risk.taxpayer_id = ent.taxpayer_id\nWHERE risk.taxpayer_id = :taxpayer_id\nORDER BY risk.risk_level DESC, risk.indicator_name ASC;',
        reasoning: '执行层最终还是会落到 SQL。\n区别不在于是否执行 SQL，而在于 SQL 的来源是否来自语义绑定。\n这里应该展示 semantic_binding、compiled SQL 和 evidence rows 三者的关系。'
      },
      'sql-fallback': {
        title: 'SQL Fallback',
        meta: ['Executor', 'fallback', 'exception path'],
        summary: '只有在语义模型没有覆盖某个字段、某个 join 或某个异常明细时，才允许退回显式 SQL。',
        semantic: ['fact_tax_risk_indicator'],
        tools: ['sql_executor'],
        evidence: ['fallback reason: composite model missing field', '保留 fallback reason，避免 SQL 退化成默认路径'],
        sql: `SELECT *
FROM tax_risk_indicators
WHERE taxpayer_id = :taxpayer_id
  AND risk_level IN ('高', '中');`,
        reasoning: 'fallback 是异常路径，不是默认路径。\nUI 上应该把 fallback 强调成“降级执行”，而不是和正常节点混成一样的观感。'
      },
      'evidence-materialize': {
        title: '证据物化',
        meta: ['Executor', 'evidence', 'cards'],
        summary: '把执行结果重组为 Evidence Cards，便于 Reviewer 和最终 Answer 直接引用。',
        semantic: ['fact_tax_risk_indicator'],
        tools: ['table renderer', 'evidence packer'],
        evidence: ['高风险指标 2 项', '风险阈值越界 1 项', '预警说明 2 条'],
        sql: '/* evidence cards generated from semantic_query result */',
        reasoning: '让 Evidence 先成为中间产物，可以把 SQL、原始表格和最终回答之间的距离拉短。\n这也是 Inspector 应该补强的一层。'
      },
      'reviewer-check': {
        title: 'Reviewer Evidence Gate',
        meta: ['Reviewer', 'approve', 'evidence gate'],
        summary: 'Reviewer 不只是审查“看起来像对的”，而是审查实体过滤是否正确、风险等级是否充分、证据是否支撑结论。',
        semantic: ['mart_tax_risk_alert'],
        tools: ['reviewer'],
        evidence: ['实体过滤正确：是', '语义口径一致：是', '高风险结论证据充足：是'],
        sql: '/* reviewer consumes node result + evidence, not raw SQL generation */',
        reasoning: '如果 evidence 不足，应返回 issues 和 suggestions，并把图上的节点打成 warning / reject 状态。\nUI 上 Reviewer 应该有明显的门禁感。'
      },
      'answer-node': {
        title: 'Answer Composer',
        meta: ['Answer', 'final report', 'drilldown'],
        summary: '最终回答应展示风险摘要，并允许回跳到对应节点查看 raw reasoning、语义模型、tool、SQL 和证据。',
        semantic: ['mart_tax_risk_alert'],
        tools: ['answer renderer', 'markdown'],
        evidence: ['最终结论：链龙商贸存在高风险税务指标预警', '证据来源：风险指标 / 阈值 / 预警说明', '支持 drilldown 到 executor 与 reviewer'],
        sql: '/* answer stage references evidence rather than re-running SQL */',
        reasoning: '最终回答区不应该与图断开。\n更合理的方式是让 answer 与 graph 共存，点击 answer 中的证据引用时，图上对应节点同步高亮。'
      }
    }

    let currentVariant = 'v1'
    let currentNodeId = 'semantic-retrieval'

    const variantButtons = document.querySelectorAll('[data-variant-btn]')
    const stages = document.querySelectorAll('[data-variant-stage]')
    const nodes = document.querySelectorAll('.proto-node')

    function renderInspector(nodeId) {
      const data = nodeData[nodeId]
      if (!data) return
      document.getElementById('inspector-title').textContent = data.title
      document.getElementById('summary-copy').textContent = data.summary
      document.getElementById('sql-preview').textContent = data.sql
      document.getElementById('reasoning-copy').textContent = data.reasoning
      document.getElementById('reasoning-panel').open = false

      const metaWrap = document.getElementById('inspector-meta')
      const semanticWrap = document.getElementById('semantic-badges')
      const toolWrap = document.getElementById('tool-badges')
      const evidenceWrap = document.getElementById('evidence-list')
      metaWrap.innerHTML = ''
      semanticWrap.innerHTML = ''
      toolWrap.innerHTML = ''
      evidenceWrap.innerHTML = ''

      data.meta.forEach(item => {
        const badge = document.createElement('span')
        badge.className = 'badge'
        badge.textContent = item
        metaWrap.appendChild(badge)
      })
      data.semantic.forEach(item => {
        const badge = document.createElement('span')
        badge.className = 'badge'
        badge.textContent = item
        semanticWrap.appendChild(badge)
      })
      data.tools.forEach(item => {
        const badge = document.createElement('span')
        badge.className = 'badge'
        badge.textContent = item
        toolWrap.appendChild(badge)
      })
      data.evidence.forEach(item => {
        const li = document.createElement('li')
        li.textContent = item
        evidenceWrap.appendChild(li)
      })
    }

    function renderVariant(variant) {
      currentVariant = variant
      document.getElementById('canvas-title').textContent = variantMeta[variant].title
      document.getElementById('canvas-subtitle').textContent = variantMeta[variant].subtitle
      variantButtons.forEach(button => {
        button.classList.toggle('active', button.getAttribute('data-variant-btn') === variant)
      })
      stages.forEach(stage => {
        stage.classList.toggle('active', stage.getAttribute('data-variant-stage') === variant)
      })
      nodes.forEach(node => {
        const active = node.getAttribute('data-variant') === variant && node.getAttribute('data-node-id') === currentNodeId
        node.classList.toggle('active', active)
      })
    }

    variantButtons.forEach(button => {
      button.addEventListener('click', () => renderVariant(button.getAttribute('data-variant-btn')))
    })
    nodes.forEach(node => {
      node.addEventListener('click', () => {
        currentNodeId = node.getAttribute('data-node-id')
        renderVariant(currentVariant)
        renderInspector(currentNodeId)
      })
    })

    renderVariant(currentVariant)
    renderInspector(currentNodeId)
  