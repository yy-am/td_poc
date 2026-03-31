<template>
  <div class="inspector-panel">
    <header class="inspector-header">
      <div>
        <span class="inspector-kicker">Inspector</span>
        <h3>{{ eventHeadline }}</h3>
      </div>
      <div class="header-badges">
        <span class="badge">{{ agentLabel }}</span>
        <span class="badge">{{ typeLabel }}</span>
        <span v-if="semanticBinding" class="badge" :class="`mode-${queryMode.kind}`">{{ queryMode.label }}</span>
        <span v-if="event.metadata?.duration_ms" class="badge">{{ event.metadata.duration_ms }}ms</span>
        <button v-if="isStageEvent" type="button" class="eye-toggle" @click="showThoughts = !showThoughts">
          <span>摘要</span>
          <span>{{ showThoughts ? '隐藏阶段摘要' : '查看阶段摘要' }}</span>
        </button>
      </div>
    </header>

    <section class="section-card">
      <span class="section-kicker">Overview</span>
      <div class="overview-grid">
        <div class="overview-item">
          <span>阶段</span>
          <strong>{{ stageLabel }}</strong>
        </div>
        <div class="overview-item">
          <span>节点</span>
          <strong>{{ overviewNodeLabel }}</strong>
        </div>
        <div class="overview-item">
          <span>工具</span>
          <strong>{{ metadata.tool_label || metadata.tool_name || '未调用' }}</strong>
        </div>
        <div class="overview-item">
          <span>查询模式</span>
          <strong>{{ queryMode.label }}</strong>
        </div>
        <div class="overview-item">
          <span>结果</span>
          <strong>{{ overviewResultLabel }}</strong>
        </div>
      </div>
      <p class="section-copy">{{ event.content }}</p>
    </section>

    <section v-if="isStageEvent" class="section-card">
      <span class="section-kicker">LLM 调用</span>
      <div v-if="stageLlmTraces.length" class="llm-trace-list">
        <article
          v-for="trace in stageLlmTraces"
          :key="`${trace.llm_call_index}-${trace.operation || ''}-${trace.timestamp || ''}`"
          class="llm-trace-card"
        >
          <div class="llm-trace-top">
            <strong>LLM#{{ trace.llm_call_index || '?' }}</strong>
            <span>{{ trace.agent || 'agent' }}</span>
            <span>{{ trace.operation || 'operation' }}</span>
            <span>{{ trace.model || 'unknown model' }}</span>
          </div>
          <div v-if="trace.node_title" class="llm-trace-node">节点 {{ trace.node_title }}</div>
          <div v-if="trace.user_prompt_preview" class="json-block compact">
            <span>Prompt 摘要</span>
            <pre>{{ trace.user_prompt_preview }}</pre>
          </div>
          <div class="json-block compact">
            <span>模型返回摘要</span>
            <pre>{{ trace.thinking || trace.raw_content_preview || '无可展示摘要' }}</pre>
          </div>
        </article>
      </div>
      <p v-else class="section-copy">当前阶段没有采集到可展示的 LLM 调用痕迹。</p>
    </section>

    <section v-if="isStageEvent" class="section-card">
      <span class="section-kicker">阶段摘要</span>
      <div v-if="showThoughts" class="thought-list">
        <p v-if="!thoughtItems.length" class="section-copy">当前阶段没有可展示的阶段摘要。</p>
        <ul v-else class="plain-list">
          <li v-for="(item, index) in thoughtItems" :key="`${index}-${item}`">{{ item }}</li>
        </ul>
      </div>
      <p v-else class="section-copy">已折叠阶段摘要，可点击右上角按钮展开。</p>
    </section>

    <section v-if="stageContextItems.length" class="section-card">
      <span class="section-kicker">Stage Context</span>
      <div class="overview-grid">
        <div v-for="item in stageContextItems" :key="`${item.label}-${item.value}`" class="overview-item">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </section>

    <section v-if="isIntentRecognitionStage && hasUnderstandingDetails" class="section-card">
      <span class="section-kicker">意图识别结果</span>
      <div class="overview-grid">
        <div v-if="understandingQueryModeLabel" class="overview-item">
          <span>查询模式</span>
          <strong>{{ understandingQueryModeLabel }}</strong>
        </div>
        <div v-if="understandingConfidenceLabel" class="overview-item">
          <span>置信度</span>
          <strong>{{ understandingConfidenceLabel }}</strong>
        </div>
        <div v-if="understandingBusinessGoal" class="overview-item overview-item-wide">
          <span>业务目标</span>
          <strong>{{ understandingBusinessGoal }}</strong>
        </div>
      </div>

      <div v-if="understandingEntityDisplays.length" class="term-group">
        <span class="term-title">实体</span>
        <div class="chip-row">
          <span v-for="item in understandingEntityDisplays" :key="item" class="chip chip-soft">{{ item }}</span>
        </div>
      </div>

      <div v-if="understandingPeriodDisplays.length" class="term-group">
        <span class="term-title">期间</span>
        <div class="chip-row">
          <span v-for="item in understandingPeriodDisplays" :key="item" class="chip chip-soft">{{ item }}</span>
        </div>
      </div>

      <div v-if="understandingCandidateModelDisplays.length" class="term-group">
        <span class="term-title">候选模型</span>
        <div class="chip-row">
          <span v-for="item in understandingCandidateModelDisplays" :key="item" class="chip">{{ item }}</span>
        </div>
      </div>

      <div v-if="understandingSemanticScopeDisplays.length" class="term-group">
        <span class="term-title">语义范围</span>
        <ul class="plain-list">
          <li v-for="item in understandingSemanticScopeDisplays" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div v-if="understandingMetricDisplays.length" class="term-group">
        <span class="term-title">识别指标</span>
        <div class="chip-row">
          <span v-for="item in understandingMetricDisplays" :key="item" class="chip">{{ item }}</span>
        </div>
      </div>

      <div v-if="understandingDimensionDisplays.length" class="term-group">
        <span class="term-title">识别维度</span>
        <div class="chip-row">
          <span v-for="item in understandingDimensionDisplays" :key="item" class="chip chip-soft">{{ item }}</span>
        </div>
      </div>

      <div v-if="understandingComparisonDisplays.length" class="term-group">
        <span class="term-title">对比关系</span>
        <ul class="plain-list">
          <li v-for="item in understandingComparisonDisplays" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div v-if="understandingRequiredEvidence.length" class="term-group">
        <span class="term-title">所需证据</span>
        <ul class="plain-list">
          <li v-for="item in understandingRequiredEvidence" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div v-if="understandingResolutionRequirements.length" class="term-group">
        <span class="term-title">解析要求</span>
        <ul class="plain-list">
          <li v-for="item in understandingResolutionRequirements" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div v-if="understandingAmbiguities.length" class="term-group">
        <span class="term-title">待澄清点</span>
        <ul class="plain-list issue-list">
          <li v-for="item in understandingAmbiguities" :key="item">{{ item }}</li>
        </ul>
      </div>
    </section>

    <section v-if="semanticBinding" class="section-card">
      <span class="section-kicker">Semantic Binding</span>
      <div class="mode-banner" :class="`mode-${queryMode.kind}`">
        <strong>{{ queryMode.label }}</strong>
        <span>{{ queryMode.detail }}</span>
      </div>

      <div class="binding-grid">
        <div v-if="entryModelDisplay" class="binding-item">
          <span>入口模型</span>
          <strong>{{ entryModelDisplay }}</strong>
        </div>
        <div v-if="candidateModelDisplays.length" class="binding-item">
          <span>候选模型</span>
          <strong>{{ candidateModelDisplays.join(' / ') }}</strong>
        </div>
        <div v-if="semanticBinding.query_language" class="binding-item">
          <span>查询语言</span>
          <strong>{{ semanticBinding.query_language }}</strong>
        </div>
        <div v-if="timeContextLabel" class="binding-item">
          <span>时间</span>
          <strong>{{ timeContextLabel }}</strong>
        </div>
      </div>

      <div v-if="metricDisplays.length" class="term-group">
        <span class="term-title">指标 Metrics</span>
        <div class="chip-row">
          <span v-for="item in metricDisplays" :key="item" class="chip">{{ item }}</span>
        </div>
      </div>

      <div v-if="dimensionDisplays.length" class="term-group">
        <span class="term-title">维度 Dimensions</span>
        <div class="chip-row">
          <span v-for="item in dimensionDisplays" :key="item" class="chip chip-soft">{{ item }}</span>
        </div>
      </div>

      <div v-if="detailFieldDisplays.length" class="term-group">
        <span class="term-title">下钻字段 Drilldown Fields</span>
        <div class="chip-row">
          <span v-for="item in detailFieldDisplays" :key="item" class="chip chip-soft">{{ item }}</span>
        </div>
      </div>

      <div v-if="compareSummary" class="json-block compact">
        <span>对比信息</span>
        <pre>{{ compareSummary }}</pre>
      </div>
      <div v-if="drilldownSummary" class="json-block compact">
        <span>下钻信息</span>
        <pre>{{ drilldownSummary }}</pre>
      </div>
      <div v-if="hasEntityFilters" class="json-block">
        <span>业务过滤</span>
        <pre>{{ formatJson(semanticBinding.entity_filters) }}</pre>
      </div>
      <div v-if="hasResolvedFilters" class="json-block">
        <span>已解析过滤</span>
        <pre>{{ formatJson(semanticBinding.resolved_filters) }}</pre>
      </div>
    </section>

    <section v-if="isTdaMqlDraftStage && tdaMqlDraftPreview" class="section-card">
      <span class="section-kicker">TDA-MQL 草稿</span>
      <div class="code-block">
        <span>{{ tdaMqlPreviewSourceLabel }}</span>
        <pre>{{ tdaMqlDraftPreview }}</pre>
      </div>
    </section>

    <section v-if="isPlanningStage && planningItems.length" class="section-card">
      <span class="section-kicker">计划拆解</span>
      <ul class="plain-list">
        <li v-for="item in planningItems" :key="item">{{ item }}</li>
      </ul>
    </section>

    <section v-if="hasToolInfo" class="section-card">
      <span class="section-kicker">工具与证据</span>
      <div class="tool-card">
        <strong>{{ metadata.tool_label || metadata.tool_name }}</strong>
        <p>{{ metadata.tool_summary || metadata.tool_input_summary || '工具执行中或已返回结果。' }}</p>
      </div>

      <div v-if="metadata.sql_preview || metadata.sql" class="code-block">
        <span>SQL 预览</span>
        <pre>{{ metadata.sql_preview || metadata.sql }}</pre>
      </div>

      <div v-if="metadata.table_data" class="table-section">
        <el-table :data="tableRows" size="small" stripe max-height="240" class="result-table">
          <el-table-column
            v-for="column in metadata.table_data.columns"
            :key="column"
            :prop="column"
            :label="column"
            min-width="120"
            show-overflow-tooltip
          />
        </el-table>
      </div>

      <div v-if="metadata.chart_config" class="chart-section">
        <ChartRenderer :option="metadata.chart_config" />
      </div>
    </section>

    <section v-if="hasReviewInfo" class="section-card">
      <span class="section-kicker">System Judgement</span>
      <div v-if="metadata.verdict" :class="['verdict-pill', metadata.verdict]">
        {{ metadata.verdict === 'approve' ? 'PASS' : 'REJECT' }}
      </div>
      <p v-if="metadata.reasoning" class="section-copy">{{ metadata.reasoning }}</p>

      <ul v-if="metadata.review_points?.length" class="plain-list">
        <li v-for="point in metadata.review_points" :key="point">{{ point }}</li>
      </ul>
      <ul v-if="metadata.issues?.length" class="plain-list issue-list">
        <li v-for="issue in metadata.issues" :key="issue">{{ issue }}</li>
      </ul>
      <ul v-if="metadata.suggestions?.length" class="plain-list suggestion-list">
        <li v-for="suggestion in metadata.suggestions" :key="suggestion">{{ suggestion }}</li>
      </ul>
    </section>

    <section v-if="metadata.evidence?.length" class="section-card">
      <span class="section-kicker">证据</span>
      <ul class="plain-list">
        <li v-for="evidence in metadata.evidence" :key="evidence">{{ evidence }}</li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getSemanticQueryMode, getStageLabel, type AgentEvent, type PlanGraph, type SemanticBindingInfo } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

const props = defineProps<{
  event: AgentEvent
  events?: AgentEvent[]
  selectedIndex?: number | null
}>()

const showThoughts = ref(true)

const TERM_LABELS: Record<string, string> = {
  vat_declared_revenue: '增值税申报收入',
  acct_book_revenue: '会计账面收入',
  revenue_gap_amount: '收入差异金额',
  revenue_gap_rate: '收入差异率',
  vat_vs_acct_diff: '税会差异',
  cit_vs_acct_diff: '所得税税会差异',
  enterprise_name: '企业名称',
  taxpayer_id: '纳税人识别号',
  period: '期间',
  tax_period: '税期',
}

const LABEL_TO_TERM = Object.entries(TERM_LABELS).reduce<Record<string, string>>((acc, [term, label]) => {
  acc[label] = term
  return acc
}, {})

const allEvents = computed<AgentEvent[]>(() => (props.events?.length ? props.events : [props.event]))

const resolvedSelectedIndex = computed(() => {
  if (typeof props.selectedIndex === 'number' && props.selectedIndex >= 0) return props.selectedIndex
  const idx = allEvents.value.findIndex(item => item === props.event)
  if (idx >= 0) return idx
  return Math.max(allEvents.value.length - 1, 0)
})

const metadata = computed<Record<string, any>>(() => toRecord(props.event.metadata))
const currentStageId = computed(() => asString(metadata.value.stage_id))
const isStageEvent = computed(() => props.event.type === 'stage_update' && Boolean(currentStageId.value))
const isIntentRecognitionStage = computed(() => currentStageId.value === 'intent_recognition')
const isTdaMqlDraftStage = computed(() => currentStageId.value === 'tda_mql_draft')
const isPlanningStage = computed(() => currentStageId.value === 'planning')

const agentLabel = computed(() => {
  const labels: Record<string, string> = {
    planner: 'Planner',
    executor: 'Executor',
    reviewer: 'Reviewer',
    orchestrator: 'System',
  }
  return labels[props.event.agent] || props.event.agent
})

const typeLabel = computed(() => {
  const labels: Record<string, string> = {
    stage_update: 'Stage',
    plan: 'Plan',
    plan_update: 'Update',
    thinking: 'Think',
    action: 'Action',
    observation: '证据',
    review: 'Review',
    answer: '回答',
    error: 'Error',
  }
  return labels[props.event.type] || props.event.type
})

const stageLabel = computed(() => {
  const stageId = currentStageId.value || asString(metadata.value.stage_status)
  return getStageLabel(stageId)
})

const eventHeadline = computed(() => {
  return metadata.value.node_title || metadata.value.tool_label || metadata.value.tool_name || stageLabel.value || '事件详情'
})

const stageNode = computed<Record<string, any> | null>(() => {
  const stageId = currentStageId.value
  const nodes = metadata.value.stage_graph?.nodes
  if (!stageId || !Array.isArray(nodes)) return null
  const found = nodes.find((item: any) => asString(item?.id) === stageId)
  return found && typeof found === 'object' ? (found as Record<string, any>) : null
})

const stageContextMetadata = computed<Record<string, any>>(() => toRecord(stageNode.value?.stage_metadata))

const stagePayload = computed<Record<string, any>>(() => {
  const direct = toRecord(metadata.value.stage_payload)
  if (Object.keys(direct).length) return direct
  return toRecord(stageContextMetadata.value.stage_payload)
})

const semanticBindingDisplay = computed<Record<string, any>>(() => {
  const direct = toRecord(metadata.value.semantic_binding_display)
  if (Object.keys(direct).length) return direct

  const fromStage = toRecord(stageContextMetadata.value.semantic_binding_display)
  if (Object.keys(fromStage).length) return fromStage

  const fromPayload = toRecord(stagePayload.value)
  if (Object.keys(fromPayload).length) return fromPayload
  return {}
})

const semanticBinding = computed<SemanticBindingInfo | null>(() => {
  const direct = toRecord(metadata.value.semantic_binding)
  if (Object.keys(direct).length) return direct as SemanticBindingInfo

  const stageBinding = toRecord(stageContextMetadata.value.semantic_binding)
  if (Object.keys(stageBinding).length) return stageBinding as SemanticBindingInfo

  const payloadBinding = toRecord(stagePayload.value.semantic_binding)
  if (Object.keys(payloadBinding).length) return payloadBinding as SemanticBindingInfo

  return null
})

const queryMode = computed(() => getSemanticQueryMode(semanticBinding.value))

const relevantModels = computed<Record<string, any>[]>(() => {
  const candidates = semanticBindingDisplay.value.candidate_models
  if (!Array.isArray(candidates)) return []
  return candidates.filter(item => item && typeof item === 'object') as Record<string, any>[]
})

const modelLabelMap = computed(() => {
  const map = new Map<string, string>()
  relevantModels.value.forEach(model => {
    const name = asString(model.name)
    const label = asString(model.label)
    if (name && label) map.set(name, label)
  })
  return map
})

const entryModelDisplay = computed(() => {
  const entry = semanticBindingDisplay.value.entry_model
  if (entry && typeof entry === 'object') {
    const displayName = asString((entry as Record<string, any>).display_name)
    const name = asString((entry as Record<string, any>).name)
    const label = asString((entry as Record<string, any>).label)
    if (displayName) return displayName
    return formatModelDisplay(name, modelLabelMap.value, label)
  }
  return formatModelDisplay(asString(semanticBinding.value?.entry_model), modelLabelMap.value)
})

const candidateModelDisplays = computed(() => {
  const values: string[] = []
  relevantModels.value.forEach(model => {
    const display = asString(model.display_name) || formatModelDisplay(asString(model.name), modelLabelMap.value, asString(model.label))
    pushUnique(values, display)
  })
  return values.slice(0, 6)
})

const metricDisplays = computed(() => {
  const source = semanticBindingDisplay.value.metrics ?? semanticBinding.value?.metrics ?? []
  return asDisplayTerms(source)
})

const dimensionDisplays = computed(() => {
  const source = semanticBindingDisplay.value.dimensions ?? semanticBinding.value?.dimensions ?? []
  return asDisplayTerms(source)
})

const detailFieldDisplays = computed(() => {
  const source = semanticBindingDisplay.value.detail_fields ?? queryMode.value.drilldown?.detail_fields ?? []
  return asDisplayTerms(source)
})

const timeContextLabel = computed(() => {
  const timeContext = toRecord(semanticBindingDisplay.value.time_context)
  const grain = asString(timeContext.grain || semanticBinding.value?.time_context?.grain)
  const range = asString(timeContext.range || semanticBinding.value?.time_context?.range)
  return [grain, range].filter(Boolean).join(' / ')
})

const compareSummary = computed(() => {
  const compare = queryMode.value.compare
  if (!compare) return ''
  return [
    compare.baseline ? `基线 ${compare.baseline}` : '',
    compare.target ? `目标 ${compare.target}` : '',
    compare.metrics?.length ? `指标 ${asDisplayTerms(compare.metrics).slice(0, 3).join(' / ')}` : '',
    compare.dimensions?.length ? `维度 ${asDisplayTerms(compare.dimensions).slice(0, 3).join(' / ')}` : '',
  ]
    .filter(Boolean)
    .join(' / ')
})

const drilldownSummary = computed(() => {
  const drilldown = queryMode.value.drilldown
  if (!drilldown) return ''
  return [
    drilldown.target ? `目标 ${formatTermDisplay(asString(drilldown.target))}` : '',
    drilldown.detail_fields?.length ? `字段 ${asDisplayTerms(drilldown.detail_fields).slice(0, 4).join(' / ')}` : '',
    typeof drilldown.limit === 'number' ? `限制 ${drilldown.limit}` : '',
  ]
    .filter(Boolean)
    .join(' / ')
})

const hasEntityFilters = computed(() => Boolean(Object.keys(toRecord(semanticBinding.value?.entity_filters)).length))
const hasResolvedFilters = computed(() => Boolean(Object.keys(toRecord(semanticBinding.value?.resolved_filters)).length))

const stageWindow = computed(() => {
  if (!isStageEvent.value) return null
  const anchor = resolvedSelectedIndex.value
  if (anchor < 0 || anchor >= allEvents.value.length) return null

  let start = 0
  for (let idx = anchor - 1; idx >= 0; idx -= 1) {
    const item = allEvents.value[idx]
    if (item.type !== 'stage_update') continue
    const sid = asString(item.metadata?.stage_id)
    if (sid !== currentStageId.value) {
      start = idx + 1
      break
    }
  }

  let end = allEvents.value.length - 1
  for (let idx = anchor + 1; idx < allEvents.value.length; idx += 1) {
    const item = allEvents.value[idx]
    if (item.type !== 'stage_update') continue
    const sid = asString(item.metadata?.stage_id)
    if (sid !== currentStageId.value) {
      end = idx - 1
      break
    }
  }

  if (start > end) return null
  return { start, end }
})

const stageLlmTraces = computed(() => {
  const direct = normalizeStageLlmTraces(metadata.value.stage_llm_traces)
  if (direct.length) return direct
  return normalizeStageLlmTraces(stageContextMetadata.value.stage_llm_traces)
})

const understandingResult = computed<Record<string, any>>(() => {
  return toRecord(metadata.value.understanding_result || stageContextMetadata.value.understanding_result)
})

const understandingQueryModeLabel = computed(() => {
  const mode = asString(understandingResult.value.query_mode)
  const labels: Record<string, string> = {
    metadata: '元数据查询',
    fact_query: '事实查询',
    analysis: '分析',
    reconciliation: '对账',
    diagnosis: '诊断',
  }
  return labels[mode] || mode
})

const understandingConfidenceLabel = computed(() => {
  const confidence = asString(understandingResult.value.confidence)
  const labels: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
  }
  return labels[confidence] || confidence
})

const understandingBusinessGoal = computed(() => {
  return asString(understandingResult.value.business_goal)
})

const understandingEntityDisplays = computed(() => {
  const entities = toRecord(understandingResult.value.entities)
  const values: string[] = []
  asStringArray(entities.enterprise_names).forEach(item => pushUnique(values, `企业：${item}`))
  asStringArray(entities.taxpayer_ids).forEach(item => pushUnique(values, `纳税人识别号：${item}`))
  asStringArray(entities.tax_types).forEach(item => pushUnique(values, `税种：${item}`))
  return values
})

const understandingPeriodDisplays = computed(() => {
  const entities = toRecord(understandingResult.value.entities)
  return asStringArray(entities.periods)
})

const understandingCandidateModelDisplays = computed(() => {
  return asStringArray(understandingResult.value.candidate_models).map(item => formatModelDisplay(item, modelLabelMap.value))
})

const understandingSemanticScopeDisplays = computed(() => {
  const scope = toRecord(understandingResult.value.semantic_scope)
  const groups: Array<{ label: string; key: string }> = [
    { label: '实体模型', key: 'entity_models' },
    { label: '原子事实模型', key: 'atomic_models' },
    { label: '复合主题模型', key: 'composite_models' },
  ]
  const values: string[] = []
  groups.forEach(group => {
    const models = asStringArray(scope[group.key]).map(item => formatModelDisplay(item, modelLabelMap.value))
    if (models.length) {
      values.push(`${group.label}：${models.join(' / ')}`)
    }
  })
  return values
})

const understandingMetricDisplays = computed(() => asDisplayTerms(understandingResult.value.metrics))
const understandingDimensionDisplays = computed(() => asDisplayTerms(understandingResult.value.dimensions))

const understandingComparisonDisplays = computed(() => {
  const comparisons = Array.isArray(understandingResult.value.comparisons) ? understandingResult.value.comparisons : []
  return comparisons
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, any>
      const left = formatTermDisplay(asString(record.left))
      const right = formatTermDisplay(asString(record.right))
      const operator = asString(record.operator) || 'compare'
      return [left, operator, right].filter(Boolean).join(' ')
    })
    .filter(Boolean)
})

const understandingRequiredEvidence = computed(() => asStringArray(understandingResult.value.required_evidence))
const understandingResolutionRequirements = computed(() => asStringArray(understandingResult.value.resolution_requirements))
const understandingAmbiguities = computed(() => asStringArray(understandingResult.value.ambiguities))

const hasUnderstandingDetails = computed(() => {
  return Boolean(
    understandingQueryModeLabel.value
    || understandingConfidenceLabel.value
    || understandingBusinessGoal.value
    || understandingEntityDisplays.value.length
    || understandingPeriodDisplays.value.length
    || understandingCandidateModelDisplays.value.length
    || understandingSemanticScopeDisplays.value.length
    || understandingMetricDisplays.value.length
    || understandingDimensionDisplays.value.length
    || understandingComparisonDisplays.value.length
    || understandingRequiredEvidence.value.length
    || understandingResolutionRequirements.value.length
    || understandingAmbiguities.value.length
  )
})

const thoughtItems = computed(() => {
  if (!isStageEvent.value) return []
  const values: string[] = []

  stageLlmTraces.value.forEach(trace => {
    pushUnique(values, formatStageLlmTrace(trace))
  })
  asStringArray(metadata.value.stage_reasoning).forEach(item => pushUnique(values, item))
  asStringArray(stageContextMetadata.value.stage_reasoning).forEach(item => pushUnique(values, item))

  const window = stageWindow.value
  if (window) {
    for (let idx = window.start; idx <= window.end; idx += 1) {
      const item = allEvents.value[idx]
      const itemStageId = asString(item.metadata?.stage_id)
      if (item.type === 'thinking' && itemStageId === currentStageId.value) {
        pushUnique(values, item.content)
      }
      if (item.type === 'stage_update' && itemStageId === currentStageId.value) {
        normalizeStageLlmTraces(item.metadata?.stage_llm_traces).forEach(trace => {
          pushUnique(values, formatStageLlmTrace(trace))
        })
      }
    }
  }

  if (!values.length) {
    const center = resolvedSelectedIndex.value
    const start = Math.max(0, center - 6)
    const end = Math.min(allEvents.value.length - 1, center + 6)
    for (let idx = start; idx <= end; idx += 1) {
      const item = allEvents.value[idx]
      if (item.type === 'thinking' && asString(item.metadata?.stage_id) === currentStageId.value) {
        pushUnique(values, item.content)
      }
    }
  }

  return values.slice(0, 24)
})

const nearestPlanGraph = computed<PlanGraph | null>(() => {
  return findNearestPlanGraph(allEvents.value, resolvedSelectedIndex.value)
})

const planningItems = computed(() => {
  const payloadNodes = Array.isArray(stagePayload.value.nodes) ? stagePayload.value.nodes : []
  const nodes = payloadNodes.length ? payloadNodes : nearestPlanGraph.value?.nodes || []

  return nodes.map(node => {
    const status = stageStatusLabel(asString(node.status))
    const title = asString(node.title) || asString(node.id)
    const detail = asString(node.detail)
    const model = asString(node.semantic_binding?.entry_model)
    const tools = asStringArray(node.tool_hints).map(item => toolLabel(item)).join(' / ')

    const pieces = [
      `${status} 路 ${title}`,
      tools ? `工具 ${tools}` : '',
      model ? `模型 ${formatModelDisplay(model, modelLabelMap.value)}` : '',
      detail,
    ].filter(Boolean)

    return pieces.join(' | ')
  })
})

const nearestMqlToolInput = computed<Record<string, any> | null>(() => {
  return findNearestMqlToolInput(allEvents.value, resolvedSelectedIndex.value)
})

const tdaMqlDraftPayload = computed<Record<string, any> | null>(() => {
  if (!isTdaMqlDraftStage.value) return null
  if (nearestMqlToolInput.value) return nearestMqlToolInput.value

  const direct = toRecord(metadata.value.tda_mql_draft)
  if (Object.keys(direct).length) return direct

  const stageDirect = toRecord(stageContextMetadata.value.tda_mql_draft)
  if (Object.keys(stageDirect).length) return stageDirect

  const payloadDraft = toRecord(stagePayload.value.tda_mql_draft)
  if (Object.keys(payloadDraft).length) return payloadDraft

  return null
})

const tdaMqlDraftPreview = computed(() => {
  if (!tdaMqlDraftPayload.value) return ''
  return formatJson(tdaMqlDraftPayload.value)
})

const tdaMqlPreviewSourceLabel = computed(() => {
  if (nearestMqlToolInput.value) return '来自执行阶段真实 mql_query 入参'
  if (Object.keys(toRecord(metadata.value.tda_mql_draft)).length) return '来自当前阶段事件 metadata.tda_mql_draft'
  if (Object.keys(toRecord(stageContextMetadata.value.tda_mql_draft)).length) return '来自 StageGraph 快照 stage_metadata.tda_mql_draft'
  if (Object.keys(toRecord(stagePayload.value.tda_mql_draft)).length) return '来自 stage_payload.tda_mql_draft'
  return '暂无真实 TDA-MQL 草稿内容'
})

const overviewNodeLabel = computed(() => {
  return metadata.value.node_title || metadata.value.node_id || stageNode.value?.title || '未指定'
})

const overviewResultLabel = computed(() => {
  if (metadata.value.result_summary) return metadata.value.result_summary
  if (metadata.value.verdict) return metadata.value.verdict
  if (metadata.value.stage_status) return stageStatusLabel(asString(metadata.value.stage_status))
  return '进行中'
})

const stageContextItems = computed(() => {
  const items: Array<{ label: string; value: string }> = []
  const stageMeta = stageContextMetadata.value
  const llmCallCount = Number(metadata.value.stage_llm_call_count ?? stageLlmTraces.value.length)
  if (!Number.isNaN(llmCallCount) && llmCallCount >= 0) {
    pushContext(items, 'LLM 调用次数', `${llmCallCount}`)
  }

  pushContext(items, '阶段状态', stageStatusLabel(asString(metadata.value.stage_status)))
  pushContext(items, '阶段说明', asString(stageNode.value?.done_when))

  if (currentStageId.value === 'intent_recognition') {
    if (typeof understandingResult.value.used_fallback === 'boolean') {
      pushContext(items, '启发式回退', understandingResult.value.used_fallback ? '是' : '否')
    }
    pushContext(items, '失败类型', asString(understandingResult.value.failure_type))
    pushContext(items, '失败说明', asString(understandingResult.value.failure_message))
    const candidateCount = asStringArray(understandingResult.value.candidate_models).length
    if (candidateCount) pushContext(items, '候选模型数', `${candidateCount}`)
  }

  if (currentStageId.value === 'semantic_binding') {
    pushContext(items, '入口模型', entryModelDisplay.value)
    pushContext(items, '候选模型', candidateModelDisplays.value.join(' / '))
    pushContext(items, '指标数', `${metricDisplays.value.length}`)
    pushContext(items, '维度数', `${dimensionDisplays.value.length}`)
  }

  if (currentStageId.value === 'tda_mql_draft') {
    pushContext(items, '入口模型', entryModelDisplay.value)
    pushContext(items, '查询语言', asString(semanticBinding.value?.query_language))
    pushContext(items, '指标', metricDisplays.value.slice(0, 4).join(' / '))
    pushContext(items, '维度', dimensionDisplays.value.slice(0, 4).join(' / '))
    pushContext(items, '时间', timeContextLabel.value)
  }

  if (currentStageId.value === 'planning') {
    pushContext(items, '计划标题', asString(stagePayload.value.title || nearestPlanGraph.value?.title))
    pushContext(items, '计划节点数', `${planningItems.value.length}`)
  }

  if (currentStageId.value === 'feasibility_assessment') {
    const count = Number(stageMeta.relevant_model_count)
    if (!Number.isNaN(count)) pushContext(items, '可用模型数', `${count}`)
    if (typeof stageMeta.resolution_ready === 'boolean') {
      pushContext(items, '实体解析就绪', stageMeta.resolution_ready ? '是' : '否')
    }
    const tools = asStringArray(stageMeta.recommended_tools).map(item => toolLabel(item)).join(' / ')
    pushContext(items, '推荐工具', tools)
  }

  if (currentStageId.value === 'metric_execution' || currentStageId.value === 'detail_execution') {
    const nodeCount = Number(stageMeta.node_count)
    const completedCount = Number(stageMeta.completed_node_count)
    if (!Number.isNaN(nodeCount)) pushContext(items, '阶段节点数', `${nodeCount}`)
    if (!Number.isNaN(completedCount)) pushContext(items, '已完成节点', `${completedCount}`)
  }

  if (currentStageId.value === 'evidence_verification') {
    const reviewableCount = Number(stageMeta.reviewable_node_count)
    const rowCount = Number(stageMeta.total_row_count)
    if (!Number.isNaN(reviewableCount)) pushContext(items, '校验节点数', `${reviewableCount}`)
    if (!Number.isNaN(rowCount)) pushContext(items, '证据行数', `${rowCount}`)
  }

  if (currentStageId.value === 'review') {
    const reviewedCount = Number(stageMeta.reviewed_node_count)
    if (!Number.isNaN(reviewedCount)) pushContext(items, '审查节点数', `${reviewedCount}`)
    if (Array.isArray(stageMeta.issues)) pushContext(items, '审查问题', `${stageMeta.issues.length}`)
  }

  if (currentStageId.value === 'report_generation') {
    const evidenceCount = Number(stageMeta.evidence_count)
    if (!Number.isNaN(evidenceCount)) pushContext(items, '引用证据数', `${evidenceCount}`)
  }

  return items
})

const hasToolInfo = computed(() => {
  return Boolean(metadata.value.tool_name || metadata.value.sql_preview || metadata.value.sql || metadata.value.table_data || metadata.value.chart_config)
})

const hasReviewInfo = computed(() => {
  return Boolean(metadata.value.verdict || metadata.value.reasoning || metadata.value.review_points?.length || metadata.value.issues?.length || metadata.value.suggestions?.length)
})

const tableRows = computed(() => {
  const tableData = metadata.value.table_data
  if (!tableData?.columns || !tableData?.rows) return []

  return tableData.rows.map((row: any) => {
    if (Array.isArray(row)) {
      const mapped: Record<string, unknown> = {}
      tableData.columns.forEach((column: string, index: number) => {
        mapped[column] = row[index]
      })
      return mapped
    }
    return row
  })
})

function toRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? (value as Record<string, any>) : {}
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(item => asString(item)).filter(Boolean)
}

type StageLlmTrace = {
  llm_call_index?: number
  timestamp?: string
  agent?: string
  operation?: string
  node_id?: string
  node_title?: string
  model?: string
  thinking?: string
  raw_content_preview?: string
  user_prompt_preview?: string
}

function normalizeStageLlmTraces(value: unknown): StageLlmTrace[] {
  if (!Array.isArray(value)) return []
  return value
    .filter(item => item && typeof item === 'object')
    .map(item => item as StageLlmTrace)
}

function formatStageLlmTrace(trace: StageLlmTrace): string {
  const idx = Number(trace.llm_call_index)
  const prefix = Number.isFinite(idx) && idx > 0 ? `LLM#${idx}` : 'LLM'
  const agent = asString(trace.agent)
  const operation = asString(trace.operation)
  const nodeTitle = asString(trace.node_title)
  const model = asString(trace.model)
  const thinking = asString(trace.thinking) || asString(trace.raw_content_preview)

  const tags = [agent, operation, nodeTitle, model].filter(Boolean).join(' / ')
  if (tags && thinking) return `${prefix} [${tags}] ${thinking}`
  if (tags) return `${prefix} [${tags}]`
  return thinking ? `${prefix} ${thinking}` : prefix
}

function stageStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '等待中',
    in_progress: '进行中',
    completed: '已完成',
    blocked: '已阻塞',
    skipped: '已跳过',
  }
  return labels[status] || status
}

function pushContext(items: Array<{ label: string; value: string }>, label: string, value: string) {
  const normalized = value.trim()
  if (!normalized) return
  items.push({ label, value: normalized })
}

function pushUnique(items: string[], value: string) {
  const normalized = value.trim()
  if (!normalized) return
  if (items.includes(normalized)) return
  items.push(normalized)
}

function formatModelDisplay(name: string, labelMap: Map<string, string>, explicitLabel = ''): string {
  const normalizedName = asString(name)
  const label = asString(explicitLabel) || labelMap.get(normalizedName) || ''
  if (normalizedName && label && normalizedName !== label) return `${label} (${normalizedName})`
  return normalizedName || label
}

function normalizeTermPair(raw: string): { en: string; zh: string; raw: string } {
  const term = asString(raw)
  if (!term) return { en: '', zh: '', raw: '' }

  const lower = term.toLowerCase()
  if (TERM_LABELS[lower]) return { en: lower, zh: TERM_LABELS[lower], raw: term }
  if (LABEL_TO_TERM[term]) return { en: LABEL_TO_TERM[term], zh: term, raw: term }

  const isAscii = /^[A-Za-z0-9_]+$/.test(term)
  if (isAscii) return { en: term, zh: TERM_LABELS[term] || '', raw: term }

  return { en: '', zh: term, raw: term }
}

function formatTermDisplay(raw: string): string {
  const pair = normalizeTermPair(raw)
  if (pair.en && pair.zh) return `${pair.en} (${pair.zh})`
  return pair.en || pair.zh || pair.raw
}

function asDisplayTerms(value: unknown): string[] {
  if (!Array.isArray(value)) {
    const single = asString(value)
    return single ? [formatTermDisplay(single)] : []
  }

  const result: string[] = []
  value.forEach(item => {
    if (item && typeof item === 'object') {
      const record = item as Record<string, any>
      const display = asString(record.display_name)
      if (display) {
        pushUnique(result, display)
        return
      }
      const name = asString(record.name)
      const label = asString(record.label)
      if (name && label && name !== label) {
        pushUnique(result, `${name} (${label})`)
        return
      }
      if (name || label) {
        pushUnique(result, name || label)
        return
      }
    }

    const text = asString(item)
    if (text) pushUnique(result, formatTermDisplay(text))
  })

  return result
}

function toolLabel(toolName: string): string {
  const labels: Record<string, string> = {
    mql_query: 'mql_query (TDA-MQL)',
    semantic_query: 'semantic_query（语义模型取数）',
    sql_executor: 'sql_executor (SQL)',
    chart_generator: 'chart_generator（图表生成）',
    metadata_query: 'metadata_query (metadata)',
    knowledge_search: 'knowledge_search（规则检索）',
  }
  return labels[toolName] || toolName
}

function findNearestPlanGraph(events: AgentEvent[], selectedIndex: number): PlanGraph | null {
  for (let idx = selectedIndex; idx >= 0; idx -= 1) {
    const event = events[idx]
    if (event.type !== 'plan' && event.type !== 'plan_update') continue
    const graph = event.metadata?.plan_graph
    if (graph && typeof graph === 'object') return graph as PlanGraph
  }

  for (let idx = selectedIndex + 1; idx < events.length; idx += 1) {
    const event = events[idx]
    if (event.type !== 'plan' && event.type !== 'plan_update') continue
    const graph = event.metadata?.plan_graph
    if (graph && typeof graph === 'object') return graph as PlanGraph
  }

  return null
}

function findNearestMqlToolInput(events: AgentEvent[], selectedIndex: number): Record<string, any> | null {
  for (let idx = selectedIndex; idx < events.length; idx += 1) {
    const event = events[idx]
    if (event.type !== 'action') continue
    if (asString(event.metadata?.tool_name) !== 'mql_query') continue
    const input = toRecord(event.metadata?.tool_input)
    if (Object.keys(input).length) return input
  }

  for (let idx = selectedIndex; idx >= 0; idx -= 1) {
    const event = events[idx]
    if (event.type !== 'action') continue
    if (asString(event.metadata?.tool_name) !== 'mql_query') continue
    const input = toRecord(event.metadata?.tool_input)
    if (Object.keys(input).length) return input
  }

  return null
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}
</script>
<style scoped>
.inspector-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(246, 250, 255, 0.82)),
    radial-gradient(circle at top right, rgba(255, 183, 100, 0.12), transparent 24%);
  box-shadow: 0 16px 34px rgba(38, 63, 95, 0.07);
}

.inspector-kicker,
.section-kicker {
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.inspector-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.inspector-header h3 {
  margin-top: 8px;
  color: var(--ink-strong);
  font-size: 26px;
  line-height: 1.08;
  letter-spacing: -0.05em;
  font-weight: 760;
}

.header-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.eye-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(89, 114, 145, 0.2);
  background: rgba(255, 255, 255, 0.9);
  color: var(--ink);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  cursor: pointer;
}

.eye-toggle:hover {
  border-color: rgba(79, 135, 255, 0.28);
  background: rgba(243, 249, 255, 0.98);
}

.badge,
.chip,
.chip-soft,
.verdict-pill {
  display: inline-flex;
  align-items: center;
  padding: 7px 10px;
  border-radius: 999px;
  font-size: 11px;
}

.badge,
.chip {
  background: rgba(79, 135, 255, 0.08);
  color: var(--ink);
}

.chip-soft {
  background: rgba(109, 216, 194, 0.12);
  color: #1c8b76;
}

.badge.mode-analysis,
.mode-banner.mode-analysis {
  background: rgba(79, 135, 255, 0.08);
  color: var(--accent-blue);
}

.badge.mode-compare,
.mode-banner.mode-compare {
  background: rgba(255, 183, 100, 0.16);
  color: #9e6414;
}

.badge.mode-drilldown,
.mode-banner.mode-drilldown {
  background: rgba(109, 216, 194, 0.16);
  color: #1c8b76;
}

.badge.mode-hybrid,
.mode-banner.mode-hybrid {
  background: rgba(137, 118, 255, 0.14);
  color: #5c49c8;
}

.section-card {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 10px 22px rgba(38, 63, 95, 0.05);
}

.overview-grid,
.binding-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.mode-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 10px;
  align-items: center;
  padding: 12px 14px;
  margin-top: 12px;
  border-radius: 16px;
  font-size: 12px;
  line-height: 1.6;
}

.mode-banner strong {
  font-size: 13px;
}

.mode-banner span {
  color: inherit;
  opacity: 0.82;
}

.overview-item,
.binding-item,
.tool-card {
  padding: 12px;
  border-radius: 16px;
  border: 1px solid rgba(89, 114, 145, 0.1);
  background: rgba(245, 249, 255, 0.8);
}

.overview-item span,
.binding-item span,
.json-block span,
.code-block span {
  display: block;
  color: var(--ink-soft);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.overview-item strong,
.binding-item strong,
.tool-card strong {
  display: block;
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 15px;
  line-height: 1.4;
}

.overview-item-wide {
  grid-column: 1 / -1;
}

.section-copy,
.tool-card p {
  margin-top: 12px;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.75;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.term-group {
  margin-top: 12px;
}

.term-title {
  display: block;
  color: var(--ink-soft);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.llm-trace-list {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.llm-trace-card {
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.1);
  background: rgba(245, 249, 255, 0.82);
}

.llm-trace-top {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.llm-trace-top strong {
  color: var(--ink-strong);
  font-size: 15px;
}

.llm-trace-top span,
.llm-trace-node {
  color: var(--ink-soft);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.llm-trace-node {
  margin-top: 10px;
}

.thought-list {
  margin-top: 10px;
}

.json-block,
.code-block {
  margin-top: 12px;
  padding: 12px;
  border-radius: 16px;
  background: rgba(241, 247, 255, 0.86);
  border: 1px solid rgba(89, 114, 145, 0.1);
}

.json-block.compact {
  background: rgba(248, 251, 255, 0.98);
}

.json-block pre,
.code-block pre {
  margin: 10px 0 0;
  color: var(--ink);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: Consolas, 'JetBrains Mono', monospace;
}

.table-section,
.chart-section {
  margin-top: 12px;
}

.verdict-pill.approve {
  background: rgba(109, 216, 194, 0.14);
  color: #1c8b76;
}

.verdict-pill.reject {
  background: rgba(227, 107, 115, 0.14);
  color: var(--accent-red);
}

.plain-list {
  margin-top: 12px;
  padding-left: 18px;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.75;
}

.issue-list {
  color: var(--accent-red);
}

.suggestion-list {
  color: #a86b12;
}

:deep(.el-table) {
  --el-table-bg-color: rgba(255, 255, 255, 0.92);
  --el-table-tr-bg-color: rgba(255, 255, 255, 0.92);
  --el-table-header-bg-color: rgba(244, 248, 255, 1);
  --el-table-border-color: rgba(89, 114, 145, 0.12);
  --el-table-text-color: #30455f;
  --el-table-header-text-color: #66788d;
  border-radius: 16px;
  overflow: hidden;
}

@media (max-width: 900px) {
  .overview-grid,
  .binding-grid {
    grid-template-columns: 1fr;
  }
}
</style>


