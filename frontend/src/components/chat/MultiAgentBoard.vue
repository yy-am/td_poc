<template>
  <div class="multi-agent-board">
    <div class="board-top">
      <div class="timeline-pane">
        <AgentTimeline
          :events="events"
          :selected-index="selectedIndex"
          @select="handleTimelineSelect"
        />
      </div>
      <div class="dag-pane">
        <PlanDAGView
          :plan-graph="latestPlanGraph"
          :active-node-id="activeNodeId"
          @select-node="handleDAGSelect"
        />
      </div>
    </div>
    <div v-if="selectedEvent" class="detail-pane">
      <AgentDetailPanel :event="selectedEvent" />
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
import AgentTimeline from './AgentTimeline.vue'
import PlanDAGView from './PlanDAGView.vue'
import AgentDetailPanel from './AgentDetailPanel.vue'

const props = defineProps<{
  steps: AgentEvent[]
  isStreaming?: boolean
}>()

const events = computed(() => props.steps)

const selectedIndex = ref<number | null>(null)
const followLatest = ref(true)

// Auto-follow latest during streaming
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
  for (let i = props.steps.length - 1; i >= 0; i--) {
    const s = props.steps[i]
    if ((s.type === 'plan' || s.type === 'plan_update') && s.metadata?.plan_graph) {
      return s.metadata.plan_graph as PlanGraph
    }
  }
  return null
})

const activeNodeId = computed(() => {
  const ev = selectedEvent.value
  if (ev?.metadata?.node_id) return ev.metadata.node_id
  const pg = latestPlanGraph.value
  if (pg?.active_node_ids?.length) return pg.active_node_ids[0]
  return ''
})

const finalAnswer = computed(() => {
  const answer = [...props.steps].reverse().find(s => s.type === 'answer')
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
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
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
.final-answer-body :deep(strong) { color: #ffa657; }
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
