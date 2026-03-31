<template>
  <div class="multi-agent-board">
    <section class="question-ribbon">
      <div class="ribbon-copy">
        <span class="ribbon-kicker">{{ runModeLabel }}</span>
        <h3 class="ribbon-question">{{ questionHeadline }}</h3>
        <p class="ribbon-summary">{{ ribbonSummary }}</p>
      </div>

      <div class="ribbon-meta">
        <div class="meta-pill">
          <span>当前阶段</span>
          <strong>{{ currentStageLabel }}</strong>
        </div>
        <div class="meta-pill">
          <span>查询模式</span>
          <strong>{{ semanticQueryMode.label }}</strong>
          <small v-if="semanticQueryMode.detail">{{ semanticQueryMode.detail }}</small>
        </div>
        <div class="meta-pill">
          <span>当前焦点</span>
          <strong>{{ currentFocusLabel }}</strong>
        </div>
        <div class="meta-pill">
          <span>最新工具</span>
          <strong>{{ latestToolLabel }}</strong>
        </div>
      </div>
    </section>

    <div class="board-shell">
      <NavigatorRail
        :events="events"
        :selected-index="selectedIndex"
        :selected-event="selectedEvent"
        @select="handleTimelineSelect"
      />

      <WorkbenchCanvas
        :plan-graph="displayGraph"
        :placeholder-text="planStatusText"
        :active-node-id="activeNodeId"
        :events="events"
        :selected-event="selectedEvent"
        @select-node="handleNodeSelect"
        @select-event="handleTimelineSelect"
      />
    </div>

    <section v-if="visibleStageInsight" class="stage-insight-panel">
      <div class="stage-insight-header">
        <div>
          <span class="stage-insight-kicker">LLM 调用证据</span>
          <h4>{{ visibleStageLabel }} 的模型调用证据</h4>
        </div>
        <div class="stage-insight-meta">
          <span class="stage-insight-pill">LLM 调用 {{ visibleStageLlmTraces.length }}</span>
          <span v-if="visibleStageReasoning.length" class="stage-insight-pill">
            阶段摘要 {{ visibleStageReasoning.length }}
          </span>
        </div>
      </div>

      <div v-if="visibleStageReasoning.length" class="reasoning-summary-list">
        <article
          v-for="(item, index) in visibleStageReasoning"
          :key="`reasoning-${index}`"
          class="reasoning-summary-card"
        >
          <span class="reasoning-summary-index">摘要 {{ index + 1 }}</span>
          <p>{{ item }}</p>
        </article>
      </div>

      <div v-if="visibleStageLlmTraces.length" class="trace-card-grid">
        <article
          v-for="trace in visibleStageLlmTraces"
          :key="`trace-${trace.llm_call_index}-${trace.operation || ''}-${trace.timestamp || ''}`"
          class="trace-card"
        >
          <div class="trace-card-top">
            <strong>LLM#{{ trace.llm_call_index || '?' }}</strong>
            <span>{{ trace.agent || 'agent' }}</span>
            <span>{{ trace.operation || 'operation' }}</span>
          </div>
          <div class="trace-card-meta">
            <span>模型 {{ trace.model || 'unknown' }}</span>
            <span v-if="trace.node_title">节点 {{ trace.node_title }}</span>
          </div>
          <div v-if="trace.user_prompt_preview" class="trace-block">
            <span>Prompt 摘要</span>
            <p>{{ trace.user_prompt_preview }}</p>
          </div>
          <div class="trace-block">
            <span>模型返回摘要</span>
            <p>{{ trace.thinking || trace.raw_content_preview || '无可展示摘要' }}</p>
          </div>
        </article>
      </div>
    </section>

    <div class="inspector-trigger-row">
      <el-button type="primary" plain :disabled="!selectedEvent" @click="openInspectorDialog">
        查看当前事件详情
      </el-button>
    </div>

    <section v-if="finalAnswer" class="final-answer-pane">
      <div class="final-answer-header">
        <span class="final-answer-kicker">报告</span>
        <h4>最终分析结论</h4>
      </div>
      <div class="final-answer-body" v-html="renderMarkdown(finalAnswer)"></div>
    </section>

    <el-dialog
      v-model="inspectorDialogVisible"
      title="当前事件详情"
      width="min(860px, 92vw)"
      align-center
      destroy-on-close
    >
      <InsightInspector
        v-if="selectedEvent"
        :event="selectedEvent"
        :events="events"
        :selected-index="selectedIndex"
      />
      <div v-else class="inspector-empty">
        <span class="inspector-empty-kicker">检查器</span>
        <h4>暂无可展示事件</h4>
        <p>请先在左侧里程碑或中间工作台选择一个事件。</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getSemanticQueryMode, getStageLabel, type AgentEvent, type PlanGraph } from '../../types/agent'
import NavigatorRail from './NavigatorRail.vue'
import WorkbenchCanvas from './WorkbenchCanvas.vue'
import InsightInspector from './InsightInspector.vue'

const props = defineProps<{
  steps: AgentEvent[]
  isStreaming?: boolean
  questionText?: string
}>()

const events = computed(() => props.steps)
const selectedIndex = ref<number | null>(null)
const followLatest = ref(true)
const inspectorDialogVisible = ref(false)

watch(
  () => props.steps.length,
  () => {
    if (followLatest.value && props.steps.length > 0) {
      selectedIndex.value = props.steps.length - 1
    }
  },
  { immediate: true },
)

const selectedEvent = computed(() => {
  if (selectedIndex.value === null) return null
  return props.steps[selectedIndex.value] ?? null
})

const latestPlanGraph = computed<PlanGraph | null>(() => {
  for (let index = props.steps.length - 1; index >= 0; index -= 1) {
    const step = props.steps[index]
    const source = step.metadata?.plan_source || step.metadata?.plan_graph?.source
    if ((step.type === 'plan' || step.type === 'plan_update') && step.metadata?.plan_graph && source === 'llm') {
      return step.metadata.plan_graph as PlanGraph
    }
  }
  return null
})

const latestStageGraph = computed<PlanGraph | null>(() => {
  for (let index = props.steps.length - 1; index >= 0; index -= 1) {
    const step = props.steps[index]
    if (step.type === 'stage_update' && step.metadata?.stage_graph) {
      return step.metadata.stage_graph as PlanGraph
    }
  }
  return null
})

const displayGraph = computed<PlanGraph | null>(() => {
  const event = selectedEvent.value
  const selectedPlanSource = event?.metadata?.plan_source || event?.metadata?.plan_graph?.source

  if (
    event?.metadata?.plan_graph &&
    (event.type === 'plan' || event.type === 'plan_update') &&
    selectedPlanSource === 'llm'
  ) {
    return event.metadata.plan_graph as PlanGraph
  }

  if (event?.metadata?.stage_graph) {
    return event.metadata.stage_graph as PlanGraph
  }

  return latestPlanGraph.value || latestStageGraph.value
})

const selectedBinding = computed(() => {
  const event = selectedEvent.value
  if (event?.metadata?.semantic_binding) return event.metadata.semantic_binding
  const activeNode = displayGraph.value?.nodes.find(node => node.id === activeNodeId.value)
  return activeNode?.semantic_binding || null
})

const semanticQueryMode = computed(() => getSemanticQueryMode(selectedBinding.value))

const planStatusText = computed(() => {
  if (displayGraph.value?.source === 'stage_graph_v0') return 'StageGraph is showing the current analysis stage.'
  if (latestPlanGraph.value) return 'Planner has produced a real executable plan.'

  const fallbackPlan = [...props.steps].reverse().find(step => {
    const source = step.metadata?.plan_source || step.metadata?.plan_graph?.source
    return (step.type === 'plan' || step.type === 'plan_update') && source && source !== 'llm'
  })

  if (fallbackPlan) {
    return 'The board only shows StageGraph and real LLM plans, not the legacy fallback plan.'
  }

  return 'Waiting for Planner to generate an execution plan.'
})

const activeNodeId = computed(() => {
  const event = selectedEvent.value
  if (event?.metadata?.node_id) return event.metadata.node_id
  if (event?.metadata?.stage_id) return event.metadata.stage_id
  const planGraph = displayGraph.value
  if (planGraph?.active_node_ids?.length) return planGraph.active_node_ids[0]
  return ''
})

const activeNodeTitle = computed(() => {
  const nodeId = activeNodeId.value
  if (!nodeId || !displayGraph.value) return ''
  return displayGraph.value.nodes.find(node => node.id === nodeId)?.title || ''
})

const currentStageId = computed(() => {
  const event = selectedEvent.value
  if (event?.metadata?.stage_id) return event.metadata.stage_id

  for (let index = props.steps.length - 1; index >= 0; index -= 1) {
    const step = props.steps[index]
    if (step.metadata?.stage_id) return step.metadata.stage_id
  }

  return ''
})

const latestToolEvent = computed(() => [...props.steps].reverse().find(step => step.metadata?.tool_name))

const finalAnswer = computed(() => {
  const answer = [...props.steps].reverse().find(step => step.type === 'answer')
  return answer?.content || ''
})

type StageLlmTraceCard = {
  llm_call_index?: number
  timestamp?: string
  agent?: string
  operation?: string
  node_title?: string
  model?: string
  thinking?: string
  raw_content_preview?: string
  user_prompt_preview?: string
}

const visibleStageInsight = computed(() => {
  if (selectedEvent.value?.type === 'stage_update' && selectedEvent.value.metadata?.stage_id) {
    return selectedEvent.value
  }
  return [...props.steps].reverse().find(
    step => step.type === 'stage_update' && (step.metadata?.stage_reasoning?.length || step.metadata?.stage_llm_traces?.length),
  ) || null
})

const visibleStageLabel = computed(() => getStageLabel(visibleStageInsight.value?.metadata?.stage_id || ''))

const visibleStageReasoning = computed(() => {
  const values = visibleStageInsight.value?.metadata?.stage_reasoning
  return Array.isArray(values)
    ? values.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
})

const visibleStageLlmTraces = computed<StageLlmTraceCard[]>(() => {
  const values = visibleStageInsight.value?.metadata?.stage_llm_traces
  if (!Array.isArray(values)) return []
  return values.filter((item): item is StageLlmTraceCard => Boolean(item && typeof item === 'object'))
})

const questionHeadline = computed(() => props.questionText?.trim() || '当前问题分析中')

const runModeLabel = computed(() => {
  if (displayGraph.value?.source === 'llm') return 'Real Execution Plan'
  if (displayGraph.value?.source === 'stage_graph_v0') return 'StageGraph v0'
  if (props.isStreaming) return 'Live Analysis'
  return 'Analysis Workspace'
})

const currentStageLabel = computed(() => getStageLabel(currentStageId.value || 'planning'))

const currentFocusLabel = computed(() => {
  const event = selectedEvent.value
  return event?.metadata?.node_title || event?.metadata?.plan_node_title || activeNodeTitle.value || '等待聚焦节点'
})

const latestToolLabel = computed(() => {
  const toolEvent = latestToolEvent.value
  return toolEvent?.metadata?.tool_label || toolEvent?.metadata?.tool_name || '尚未调用'
})

const ribbonSummary = computed(() => {
  const event = selectedEvent.value
  const binding = selectedBinding.value
  const fragments = [
    binding?.entry_model ? `入口模型 ${binding.entry_model}` : '',
    binding?.metrics?.length ? `指标 ${binding.metrics.slice(0, 2).join(' / ')}` : '',
    binding?.dimensions?.length ? `维度 ${binding.dimensions.slice(0, 2).join(' / ')}` : '',
    semanticQueryMode.value.kind !== 'analysis' ? semanticQueryMode.value.label : '',
    semanticQueryMode.value.detail ? semanticQueryMode.value.detail : '',
    latestToolEvent.value?.metadata?.tool_name ? `工具 ${latestToolLabel.value}` : '',
  ].filter(Boolean)

  if (fragments.length > 0) return fragments.join(' · ')
  if (event?.content) return event.content.slice(0, 120)
  return '系统会先展示阶段图，再逐步切换到真实计划和执行证据。'
})

function handleTimelineSelect(index: number) {
  followLatest.value = false
  selectedIndex.value = index
  inspectorDialogVisible.value = true
}

function handleNodeSelect(nodeId: string) {
  followLatest.value = false
  for (let index = props.steps.length - 1; index >= 0; index -= 1) {
    const step = props.steps[index]
    if (step.metadata?.node_id === nodeId || step.metadata?.stage_id === nodeId) {
      selectedIndex.value = index
      inspectorDialogVisible.value = true
      return
    }
  }
}

function openInspectorDialog() {
  if (!selectedEvent.value) return
  inspectorDialogVisible.value = true
}

function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n/g, '<br>')
}
</script>

<style scoped>
.multi-agent-board {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: min(1480px, 100%);
  padding: 18px;
  border-radius: 30px;
  border: 1px solid var(--line);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(247, 251, 255, 0.82)),
    radial-gradient(circle at top left, rgba(127, 215, 255, 0.18), transparent 34%);
  box-shadow: var(--shadow-panel);
}

.question-ribbon {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.95fr);
  gap: 16px;
  padding: 20px 22px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(245, 250, 255, 0.84)),
    radial-gradient(circle at top right, rgba(255, 183, 100, 0.16), transparent 26%);
}

.ribbon-copy {
  min-width: 0;
}

.ribbon-kicker,
.final-answer-kicker,
.inspector-empty-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.ribbon-question {
  margin-top: 14px;
  color: var(--ink-strong);
  font-size: 30px;
  line-height: 1.08;
  letter-spacing: -0.05em;
  font-weight: 760;
}

.ribbon-summary {
  margin-top: 10px;
  max-width: 72ch;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.ribbon-meta {
  display: grid;
  gap: 10px;
}

.meta-pill {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 10px 24px rgba(38, 63, 95, 0.08);
}

.meta-pill span {
  display: block;
  color: var(--ink-soft);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.meta-pill strong {
  display: block;
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 18px;
  line-height: 1.25;
}

.meta-pill small {
  display: block;
  margin-top: 8px;
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.5;
}

.board-shell {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  min-height: 640px;
}

.inspector-trigger-row {
  display: flex;
  justify-content: flex-end;
}

.stage-insight-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.16);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(247, 251, 255, 0.86)),
    radial-gradient(circle at top right, rgba(109, 216, 194, 0.12), transparent 28%);
  box-shadow: 0 14px 28px rgba(38, 63, 95, 0.06);
}

.stage-insight-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.stage-insight-kicker {
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.stage-insight-header h4 {
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 22px;
  letter-spacing: -0.04em;
}

.stage-insight-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.stage-insight-pill {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(79, 135, 255, 0.18);
  background: rgba(79, 135, 255, 0.08);
  color: var(--ink-strong);
  font-size: 12px;
  font-weight: 600;
}

.reasoning-summary-list {
  display: grid;
  gap: 10px;
}

.reasoning-summary-card,
.trace-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 10px 20px rgba(38, 63, 95, 0.05);
}

.reasoning-summary-index {
  display: inline-flex;
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.reasoning-summary-card p {
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.trace-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.trace-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.trace-card-top {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.trace-card-top strong {
  color: var(--ink-strong);
  font-size: 15px;
}

.trace-card-top span,
.trace-card-meta span,
.trace-block span {
  color: var(--ink-soft);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.trace-card-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.trace-block {
  display: grid;
  gap: 6px;
}

.trace-block p {
  margin: 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.inspector-empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 100%;
  padding: 24px;
  border-radius: 24px;
  border: 1px dashed rgba(89, 114, 145, 0.22);
  background: rgba(255, 255, 255, 0.68);
}

.inspector-empty h4 {
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 22px;
  letter-spacing: -0.04em;
  font-weight: 740;
}

.inspector-empty p {
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.final-answer-pane {
  padding: 22px 24px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(247, 251, 255, 0.82)),
    radial-gradient(circle at top left, rgba(109, 216, 194, 0.14), transparent 24%);
}

.final-answer-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.final-answer-header h4 {
  color: var(--ink-strong);
  font-size: 24px;
  letter-spacing: -0.04em;
  font-weight: 760;
}

.final-answer-body {
  margin-top: 14px;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.8;
}

.final-answer-body :deep(h2),
.final-answer-body :deep(h3),
.final-answer-body :deep(h4) {
  color: var(--ink-strong);
  margin: 10px 0 6px;
}

.final-answer-body :deep(strong) {
  color: var(--accent-blue);
}

.final-answer-body :deep(code) {
  padding: 2px 6px;
  border-radius: 8px;
  background: rgba(79, 135, 255, 0.08);
  color: var(--ink-strong);
  font-size: 12px;
}

.final-answer-body :deep(ul) {
  padding-left: 20px;
  margin: 6px 0;
}

.final-answer-body :deep(li) {
  margin: 3px 0;
}

@media (max-width: 1480px) {
  .board-shell {
    grid-template-columns: 280px minmax(0, 1fr);
  }
}

@media (max-width: 1080px) {
  .question-ribbon,
  .board-shell {
    grid-template-columns: 1fr;
  }

  .multi-agent-board {
    padding: 14px;
    border-radius: 24px;
  }
}
</style>



