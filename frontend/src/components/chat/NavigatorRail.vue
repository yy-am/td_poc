<template>
  <div class="navigator-rail">
    <header class="rail-header">
      <span class="rail-kicker">导航</span>
      <h3>过程导航</h3>
      <p>这里展示本轮分析的关键阶段、当前语义绑定和模型调用信号，帮助快速判断系统正在做什么。</p>
    </header>

    <section class="snapshot-grid">
      <div class="snapshot-card">
        <span>阶段</span>
        <strong>{{ currentStageLabel }}</strong>
      </div>
      <div class="snapshot-card">
        <span>工具</span>
        <strong>{{ currentToolLabel }}</strong>
      </div>
      <div class="snapshot-card">
        <span>入口模型</span>
        <strong>{{ currentModelLabel }}</strong>
      </div>
      <div class="snapshot-card">
        <span>查询模式</span>
        <strong :class="`query-${currentQueryModeKind}`">{{ currentQueryModeLabel }}</strong>
      </div>
      <div class="snapshot-card">
        <span>事件数</span>
        <strong>{{ visibleEvents.length }}</strong>
      </div>
    </section>

    <section class="milestone-section">
      <div class="section-head">
        <span class="section-kicker">里程碑</span>
        <strong>关键事件</strong>
      </div>

      <div class="milestone-list">
        <button
          v-for="item in visibleEvents"
          :key="item.index"
          type="button"
          :class="['milestone-card', { selected: item.index === selectedIndex }]"
          @click="$emit('select', item.index)"
        >
          <div class="milestone-top">
            <span class="milestone-icon">{{ eventIcon(item.event) }}</span>
            <span class="milestone-type">{{ eventTypeLabel(item.event.type) }}</span>
            <span v-if="eventQueryModeLabel(item.event)" class="milestone-mode">{{ eventQueryModeLabel(item.event) }}</span>
            <span v-if="eventLlmCallCount(item.event)" class="milestone-mode llm-count">
              LLM ×{{ eventLlmCallCount(item.event) }}
            </span>
          </div>
          <strong>{{ eventHeadline(item.event) }}</strong>
          <p>{{ eventCopy(item.event) }}</p>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getSemanticQueryMode, getStageLabel, type AgentEvent, type SemanticBindingInfo } from '../../types/agent'

const props = defineProps<{
  events: AgentEvent[]
  selectedIndex: number | null
  selectedEvent?: AgentEvent | null
}>()

defineEmits<{
  select: [index: number]
}>()

const currentStageLabel = computed(() => {
  const stageEvent = [...props.events].reverse().find(event => event.metadata?.stage_id)
  const stageId = props.selectedEvent?.metadata?.stage_id || stageEvent?.metadata?.stage_id || ''
  return getStageLabel(stageId)
})

const currentToolLabel = computed(() => {
  const toolEvent = props.selectedEvent?.metadata?.tool_name
    ? props.selectedEvent
    : [...props.events].reverse().find(event => event.metadata?.tool_name)

      return toolEvent?.metadata?.tool_label || toolEvent?.metadata?.tool_name || '尚未调用'
})

const currentModelLabel = computed(() => {
  const binding = props.selectedEvent?.metadata?.semantic_binding ||
    [...props.events].reverse().find(event => event.metadata?.semantic_binding)?.metadata?.semantic_binding

  return binding?.entry_model || '待绑定'
})

const currentQueryModeLabel = computed(() => {
  const binding = props.selectedEvent?.metadata?.semantic_binding ||
    [...props.events].reverse().find(event => event.metadata?.semantic_binding)?.metadata?.semantic_binding
  return getSemanticQueryMode(binding as SemanticBindingInfo | null).label
})

const currentQueryModeKind = computed(() => {
  const binding = props.selectedEvent?.metadata?.semantic_binding ||
    [...props.events].reverse().find(event => event.metadata?.semantic_binding)?.metadata?.semantic_binding
  return getSemanticQueryMode(binding as SemanticBindingInfo | null).kind
})

const visibleEvents = computed(() => {
  const latestByStage = new Map<string, { event: AgentEvent; index: number }>()

  props.events.forEach((event, index) => {
    if (event.type !== 'stage_update') return
    const stageId = event.metadata?.stage_id || `unknown_${index}`
    latestByStage.set(stageId, { event, index })
  })

  const stageOrder = [
    'intent_recognition',
    'semantic_binding',
    'tda_mql_draft',
    'feasibility_assessment',
    'planning',
    'metric_execution',
    'detail_execution',
    'evidence_verification',
    'review',
    'report_generation',
  ]

  const ordered: Array<{ event: AgentEvent; index: number }> = []

  stageOrder.forEach(stageId => {
    const item = latestByStage.get(stageId)
    if (item) ordered.push(item)
  })

  const extraStages = [...latestByStage.entries()]
    .filter(([stageId]) => !stageOrder.includes(stageId))
    .map(([, item]) => item)
    .sort((a, b) => a.index - b.index)

  return [...ordered, ...extraStages]
})

function eventIcon(event: AgentEvent): string {
  const map: Record<string, string> = {
    planner: 'PL',
    executor: 'EX',
    reviewer: 'RV',
    orchestrator: 'OR',
  }
  return map[event.agent] || 'AG'
}

function eventTypeLabel(type: string): string {
  const map: Record<string, string> = {
    stage_update: 'Stage',
    plan: 'Plan',
    plan_update: 'Update',
    thinking: 'Think',
    action: 'Action',
    observation: 'Evidence',
    review: 'Review',
    answer: 'Answer',
    error: 'Error',
  }
  return map[type] || type
}

function eventHeadline(event: AgentEvent): string {
  if (event.metadata?.stage_id) {
    return getStageLabel(event.metadata.stage_id)
  }
  return (
    event.metadata?.node_title ||
    event.metadata?.tool_label ||
    event.metadata?.tool_name ||
    event.metadata?.stage_id ||
    event.content.slice(0, 24)
  )
}

function eventCopy(event: AgentEvent): string {
  const statusMap: Record<string, string> = {
    pending: '等待中',
    in_progress: '进行中',
    completed: '已完成',
    blocked: '已阻塞',
    skipped: '已跳过',
  }

  const status = event.metadata?.stage_status ? statusMap[event.metadata.stage_status] || event.metadata.stage_status : ''
  if (status) return `${status} 路 ${event.content.slice(0, 72)}`
  return event.content.slice(0, 90)
}

function eventQueryModeLabel(event: AgentEvent): string {
  const binding = event.metadata?.semantic_binding
  if (!binding) return ''
  const summary = getSemanticQueryMode(binding as SemanticBindingInfo)
  return summary.kind === 'analysis' ? '' : summary.label
}

function eventLlmCallCount(event: AgentEvent): number {
  const count = Number(event.metadata?.stage_llm_call_count || 0)
  return Number.isFinite(count) && count > 0 ? count : 0
}
</script>

<style scoped>
.navigator-rail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(247, 251, 255, 0.82)),
    radial-gradient(circle at top left, rgba(109, 216, 194, 0.12), transparent 24%);
  box-shadow: 0 16px 34px rgba(38, 63, 95, 0.07);
}

.rail-kicker,
.section-kicker {
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.rail-header h3 {
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 24px;
  letter-spacing: -0.05em;
  font-weight: 760;
}

.rail-header p {
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.snapshot-card,
.milestone-card {
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 10px 22px rgba(38, 63, 95, 0.06);
}

.snapshot-card {
  padding: 14px;
}

.snapshot-card span {
  display: block;
  color: var(--ink-soft);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.snapshot-card strong {
  display: block;
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 16px;
  line-height: 1.35;
}

.snapshot-card strong.query-analysis {
  color: var(--accent-blue);
}

.snapshot-card strong.query-compare {
  color: #9e6414;
}

.snapshot-card strong.query-drilldown {
  color: #1c8b76;
}

.snapshot-card strong.query-hybrid {
  color: #5c49c8;
}

.milestone-section {
  flex: 1;
  min-height: 0;
}

.section-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-head strong {
  color: var(--ink-strong);
  font-size: 22px;
  letter-spacing: -0.04em;
  font-weight: 740;
}

.milestone-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.milestone-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.milestone-card:hover {
  transform: translateY(-1px);
  border-color: rgba(79, 135, 255, 0.24);
  box-shadow: 0 12px 26px rgba(79, 135, 255, 0.08);
}

.milestone-card.selected {
  border-color: rgba(79, 135, 255, 0.24);
  background: rgba(243, 249, 255, 0.96);
}

.milestone-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.milestone-icon {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(79, 135, 255, 0.08);
  font-size: 14px;
}

.milestone-type {
  color: var(--accent-blue);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.milestone-mode {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 183, 100, 0.14);
  color: #9e6414;
  font-size: 10px;
  font-weight: 700;
}

.milestone-mode.llm-count {
  background: rgba(79, 135, 255, 0.12);
  color: var(--accent-blue);
}

.milestone-card strong {
  color: var(--ink-strong);
  font-size: 15px;
  line-height: 1.4;
}

.milestone-card p {
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.6;
}
</style>

