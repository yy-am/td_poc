<template>
  <div class="multi-agent-board">
    <div class="board-top">
      <div class="timeline-pane">
        <AgentTimelineClean
          :events="events"
          :selected-index="selectedIndex"
          @select="handleTimelineSelect"
        />
      </div>
      <div class="dag-pane">
        <PlanDAGViewClean
          :plan-graph="latestPlanGraph"
          :placeholder-text="planStatusText"
          :active-node-id="activeNodeId"
          @select-node="handleDAGSelect"
        />
      </div>
    </div>

    <div v-if="selectedEvent" class="detail-pane">
      <AgentDetailPanelClean :event="selectedEvent" />
    </div>

    <div v-if="finalAnswer" class="final-answer-pane">
      <div class="final-answer-header">最终报告</div>
      <div class="final-answer-body" v-html="renderMarkdown(finalAnswer)"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AgentEvent, PlanGraph } from '../../types/agent'
import AgentTimelineClean from './AgentTimelineClean.vue'
import PlanDAGViewClean from './PlanDAGViewClean.vue'
import AgentDetailPanelClean from './AgentDetailPanelClean.vue'

const props = defineProps<{
  steps: AgentEvent[]
  isStreaming?: boolean
}>()

const events = computed(() => props.steps)

const selectedIndex = ref<number | null>(null)
const followLatest = ref(true)

watch(() => props.steps.length, () => {
  if (followLatest.value && props.steps.length > 0) {
    selectedIndex.value = props.steps.length - 1
  }
})

const selectedEvent = computed(() => {
  if (selectedIndex.value === null) return null
  return props.steps[selectedIndex.value] ?? null
})

const latestPlanGraph = computed<PlanGraph | null>(() => {
  for (let i = props.steps.length - 1; i >= 0; i -= 1) {
    const step = props.steps[i]
    const source = step.metadata?.plan_source || step.metadata?.plan_graph?.source
    if ((step.type === 'plan' || step.type === 'plan_update') && step.metadata?.plan_graph && source === 'llm') {
      return step.metadata.plan_graph as PlanGraph
    }
  }
  return null
})

const planStatusText = computed(() => {
  if (latestPlanGraph.value) return '等待 Planner 生成执行计划...'
  const fallbackPlan = [...props.steps].reverse().find(step => {
    const source = step.metadata?.plan_source || step.metadata?.plan_graph?.source
    return (step.type === 'plan' || step.type === 'plan_update') && source && source !== 'llm'
  })
  if (fallbackPlan) {
    return 'Planner 未生成真实 LLM 计划图，前端已拒绝展示保底/写死计划。'
  }
  return '等待 Planner 生成执行计划...'
})

const activeNodeId = computed(() => {
  const event = selectedEvent.value
  if (event?.metadata?.node_id) return event.metadata.node_id
  const planGraph = latestPlanGraph.value
  if (planGraph?.active_node_ids?.length) return planGraph.active_node_ids[0]
  return ''
})

const finalAnswer = computed(() => {
  const answer = [...props.steps].reverse().find(step => step.type === 'answer')
  return answer?.content || ''
})

function handleTimelineSelect(index: number) {
  followLatest.value = false
  selectedIndex.value = index
}

function handleDAGSelect(nodeId: string) {
  followLatest.value = false
  for (let i = props.steps.length - 1; i >= 0; i -= 1) {
    if (props.steps[i].metadata?.node_id === nodeId) {
      selectedIndex.value = i
      return
    }
  }
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
  gap: 0;
  background: #0d1117;
  border-radius: 12px;
  border: 1px solid #21262d;
  overflow: hidden;
  max-width: 100%;
}

.board-top {
  display: flex;
  min-height: 320px;
  max-height: 480px;
}

.timeline-pane {
  width: 35%;
  min-width: 240px;
  border-right: 1px solid #21262d;
  overflow-y: auto;
}

.dag-pane {
  flex: 1;
  overflow: auto;
  padding: 12px;
}

.detail-pane {
  border-top: 1px solid #21262d;
  max-height: 260px;
  overflow-y: auto;
}

.final-answer-pane {
  border-top: 1px solid #21262d;
  padding: 16px 20px;
  background: rgba(22, 33, 62, 0.6);
}

.final-answer-header {
  font-size: 14px;
  font-weight: 700;
  color: #58a6ff;
  margin-bottom: 10px;
}

.final-answer-body {
  font-size: 13px;
  color: #e0e0e0;
  line-height: 1.8;
}

.final-answer-body :deep(h2),
.final-answer-body :deep(h3),
.final-answer-body :deep(h4) {
  color: #c9d1d9;
  margin: 8px 0 4px;
}

.final-answer-body :deep(strong) {
  color: #ffa657;
}

.final-answer-body :deep(code) {
  background: #161b22;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}

.final-answer-body :deep(ul) {
  padding-left: 20px;
  margin: 4px 0;
}

.final-answer-body :deep(li) {
  margin: 2px 0;
}
</style>
