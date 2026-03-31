<template>
  <div class="workbench-view" :class="{ 'stage-mode': isStageGraph }">
    <div v-if="!planGraph" class="workbench-placeholder">
      <span class="placeholder-icon">⏳</span>
      <span>{{ placeholderText || '等待 Planner 生成执行计划。' }}</span>
    </div>

    <template v-else-if="activeNode">
      <header class="workbench-header">
        <div class="header-copy">
          <span class="mode-badge">{{ modeLabel }}</span>
          <h3 class="header-title">{{ planGraph.title }}</h3>
          <p class="header-summary">
            {{ planGraph.summary || '当前工作台会围绕焦点节点展示上下文、工具和最近证据。' }}
          </p>
        </div>

        <div class="header-stats">
          <div class="stat-card">
            <span>Nodes</span>
            <strong>{{ sortedNodes.length }}</strong>
          </div>
          <div class="stat-card">
            <span>Done</span>
            <strong>{{ completedCount }}</strong>
          </div>
          <div class="stat-card">
            <span>Focus</span>
            <strong>{{ activeNode.title }}</strong>
          </div>
        </div>
      </header>

      <div class="canvas-grid">
        <section class="lane-card">
          <div class="lane-kicker">Why This Step</div>
          <h4 class="lane-title">当前上下文</h4>

          <div class="lane-list">
            <button
              v-for="node in upstreamNodes"
              :key="node.id"
              type="button"
              class="lane-node"
              @click="$emit('selectNode', node.id)"
            >
              <span class="lane-node-status">{{ statusLabel(node.status) }}</span>
              <strong>{{ node.title }}</strong>
              <span>{{ node.detail }}</span>
            </button>
          </div>

        <div class="binding-card">
          <div class="binding-label">Semantic Binding</div>
          <template v-if="focusBinding">
            <div class="binding-mode-row">
              <span class="binding-mode-pill" :class="`mode-${semanticMode.kind}`">{{ semanticMode.label }}</span>
              <span v-if="semanticMode.detail" class="binding-mode-copy">{{ semanticMode.detail }}</span>
            </div>
            <div v-if="focusBinding.entry_model" class="binding-line">
              <span>入口模型</span>
              <strong>{{ focusBinding.entry_model }}</strong>
            </div>
            <div v-if="focusBinding.metrics?.length" class="binding-line">
                <span>指标</span>
                <strong>{{ focusBinding.metrics.slice(0, 3).join(' / ') }}</strong>
              </div>
              <div v-if="focusBinding.dimensions?.length" class="binding-line">
                <span>维度</span>
                <strong>{{ focusBinding.dimensions.slice(0, 3).join(' / ') }}</strong>
              </div>
            <div v-if="timeContextLabel" class="binding-line">
              <span>时间</span>
              <strong>{{ timeContextLabel }}</strong>
            </div>
            <div v-if="compareSummary" class="binding-line mode-line">
              <span>对比</span>
              <strong>{{ compareSummary }}</strong>
            </div>
            <div v-if="drilldownSummary" class="binding-line mode-line">
              <span>下钻</span>
              <strong>{{ drilldownSummary }}</strong>
            </div>
          </template>
          <p v-else class="binding-empty">当前节点没有显式语义绑定信息。</p>
        </div>
        </section>

        <section class="focus-card">
          <div class="focus-shell">
            <span class="focus-status" :class="`status-${activeNode.status}`">{{ statusLabel(activeNode.status) }}</span>
            <div class="focus-title">{{ activeNode.title }}</div>
            <div class="focus-subtitle">
              {{ nodeKindLabel(activeNode.kind) }} · {{ activeNode.id }}
            </div>
            <p class="focus-detail">
              {{ focusNarrative }}
            </p>

            <div class="focus-chips">
              <span class="focus-chip">{{ modeLabel }}</span>
              <span class="focus-chip" :class="`query-${semanticMode.kind}`">{{ semanticMode.label }}</span>
              <span v-if="currentToolLabel" class="focus-chip accent">{{ currentToolLabel }}</span>
              <span v-if="activeNode.done_when" class="focus-chip">{{ activeNode.done_when }}</span>
            </div>
          </div>

          <div class="signal-row">
            <div class="signal-card">
              <div class="signal-label">Current Action</div>
              <strong>{{ currentActionLabel }}</strong>
              <p>{{ currentActionCopy }}</p>
            </div>
            <div class="signal-card">
              <div class="signal-label">Latest Evidence</div>
              <strong>{{ latestEvidenceLabel }}</strong>
              <p>{{ latestEvidenceCopy }}</p>
            </div>
          </div>
        </section>

        <section class="lane-card next-lane">
          <div class="lane-kicker">Next Moves</div>
          <h4 class="lane-title">后续路径</h4>

          <div class="lane-list">
            <button
              v-for="node in downstreamNodes"
              :key="node.id"
              type="button"
              class="lane-node"
              @click="$emit('selectNode', node.id)"
            >
              <span class="lane-node-status">{{ statusLabel(node.status) }}</span>
              <strong>{{ node.title }}</strong>
              <span>{{ node.detail }}</span>
            </button>
          </div>

          <div class="pending-card">
            <span>Pending Nodes</span>
            <strong>{{ pendingCount }}</strong>
          </div>
        </section>
      </div>

      <div class="satellite-cloud">
        <button
          v-for="node in satelliteNodes"
          :key="node.id"
          type="button"
          :class="['satellite-node', `status-${node.status}`, { active: node.id === resolvedActiveNodeId }]"
          @click="$emit('selectNode', node.id)"
        >
          <span class="satellite-kind">{{ nodeKindLabel(node.kind) }}</span>
          <strong>{{ node.title }}</strong>
          <span>{{ statusLabel(node.status) }}</span>
        </button>
      </div>

      <section class="filmstrip">
        <div class="filmstrip-header">
          <div>
            <span class="filmstrip-kicker">Recent Stage Updates</span>
            <h4>最近阶段事件</h4>
          </div>
          <span class="filmstrip-count">{{ recentEvents.length }} items</span>
        </div>

        <div class="filmstrip-track">
          <button
            v-for="item in recentEvents"
            :key="item.index"
            type="button"
            :class="['film-card', { selected: item.index === selectedEventIndex }]"
            @click="$emit('selectEvent', item.index)"
          >
            <span class="film-type">{{ eventTypeLabel(item.event.type) }}</span>
            <strong>{{ eventHeadline(item.event) }}</strong>
            <span>{{ eventCopy(item.event) }}</span>
          </button>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getSemanticQueryMode, type AgentEvent, type PlanGraph, type PlanGraphNode, type SemanticBindingInfo } from '../../types/agent'

const props = defineProps<{
  planGraph: PlanGraph | null
  placeholderText?: string
  activeNodeId?: string
  events?: AgentEvent[]
  selectedEvent?: AgentEvent | null
}>()

defineEmits<{
  selectNode: [nodeId: string]
  selectEvent: [index: number]
}>()

const sortedNodes = computed(() => {
  if (!props.planGraph) return []

  const nodes = props.planGraph.nodes
  const nodeMap = new Map(nodes.map(node => [node.id, node]))
  const visited = new Set<string>()
  const result: PlanGraphNode[] = []

  function visit(id: string) {
    if (visited.has(id)) return
    visited.add(id)
    const node = nodeMap.get(id)
    if (!node) return
    for (const dep of node.depends_on || []) {
      visit(dep)
    }
    result.push(node)
  }

  for (const node of nodes) visit(node.id)
  return result
})

const isStageGraph = computed(() => props.planGraph?.source === 'stage_graph_v0')

const resolvedActiveNodeId = computed(() => {
  if (props.activeNodeId) return props.activeNodeId
  const inProgressNode = sortedNodes.value.find(node => node.status === 'in_progress')
  if (inProgressNode) return inProgressNode.id
  const blockedNode = sortedNodes.value.find(node => node.status === 'blocked')
  if (blockedNode) return blockedNode.id
  return sortedNodes.value[sortedNodes.value.length - 1]?.id || ''
})

const activeNode = computed(() => {
  return sortedNodes.value.find(node => node.id === resolvedActiveNodeId.value) || null
})

const completedCount = computed(() => sortedNodes.value.filter(node => node.status === 'completed').length)
const pendingCount = computed(() => sortedNodes.value.filter(node => node.status === 'pending').length)

const selectedEventIndex = computed(() => {
  if (!props.selectedEvent || !props.events?.length) return -1
  return props.events.findIndex(item => item === props.selectedEvent)
})

const upstreamNodes = computed(() => {
  if (!activeNode.value || !props.planGraph) return []
  const nodeMap = new Map(props.planGraph.nodes.map(node => [node.id, node]))
  return (activeNode.value.depends_on || [])
    .map(nodeId => nodeMap.get(nodeId))
    .filter((node): node is PlanGraphNode => Boolean(node))
    .slice(0, 3)
})

const downstreamNodes = computed(() => {
  if (!activeNode.value) return []
  return sortedNodes.value
    .filter(node => (node.depends_on || []).includes(activeNode.value!.id))
    .slice(0, 3)
})

const satelliteNodes = computed(() => {
  if (!activeNode.value) return []
  return sortedNodes.value
    .filter(node => node.id !== activeNode.value!.id)
    .slice(0, 6)
})

const latestAction = computed(() => {
  return [...(props.events || [])].reverse().find(event => event.type === 'action')
})

const latestObservation = computed(() => {
  return [...(props.events || [])].reverse().find(event =>
    ['observation', 'table', 'chart'].includes(event.type),
  )
})

const focusBinding = computed(() => {
  return (props.selectedEvent?.metadata?.semantic_binding || activeNode.value?.semantic_binding || null) as SemanticBindingInfo | null
})

const semanticMode = computed(() => getSemanticQueryMode(focusBinding.value))

const timeContextLabel = computed(() => {
  const timeContext = focusBinding.value?.time_context
  if (!timeContext) return ''
  return [timeContext.grain, timeContext.range].filter(Boolean).join(' · ')
})

const focusNarrative = computed(() => {
  if (props.selectedEvent?.content) return props.selectedEvent.content
  return activeNode.value?.detail || '当前节点正在等待更多执行信息。'
})

const currentToolLabel = computed(() => {
  const selectedTool = props.selectedEvent?.metadata?.tool_label || props.selectedEvent?.metadata?.tool_name
  if (selectedTool) return selectedTool
  return latestAction.value?.metadata?.tool_label || latestAction.value?.metadata?.tool_name || ''
})

const compareSummary = computed(() => {
  const compare = semanticMode.value.compare
  if (!compare) return ''
  return [
    compare.baseline ? `基线 ${compare.baseline}` : '',
    compare.target ? `目标 ${compare.target}` : '',
    compare.metrics?.length ? `指标 ${compare.metrics.slice(0, 2).join(' / ')}` : '',
    compare.dimensions?.length ? `维度 ${compare.dimensions.slice(0, 2).join(' / ')}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
})

const drilldownSummary = computed(() => {
  const drilldown = semanticMode.value.drilldown
  if (!drilldown) return ''
  return [
    drilldown.target ? `目标 ${drilldown.target}` : '',
    drilldown.detail_fields?.length ? `字段 ${drilldown.detail_fields.slice(0, 3).join(' / ')}` : '',
    typeof drilldown.limit === 'number' ? `限额 ${drilldown.limit}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
})

const currentActionLabel = computed(() => {
  return latestAction.value?.metadata?.node_title || latestAction.value?.metadata?.tool_name || '等待动作'
})

const currentActionCopy = computed(() => {
  return latestAction.value?.content || '当前还没有工具调用事件。'
})

const latestEvidenceLabel = computed(() => {
  return latestObservation.value?.metadata?.result_summary || latestObservation.value?.metadata?.tool_label || '等待证据'
})

const latestEvidenceCopy = computed(() => {
  return latestObservation.value?.content || '一旦执行结果返回，这里会展示结果摘要和证据信号。'
})

const modeLabel = computed(() => {
  if (props.planGraph?.source === 'llm') return 'Real Plan'
  if (props.planGraph?.source?.startsWith('stage_graph')) return 'StageGraph v1-lite'
  return 'Plan Graph'
})

const recentEvents = computed(() => {
  const candidates = (props.events || [])
    .map((event, index) => ({ event, index }))
    .filter(item => item.event.type === 'stage_update')

  return candidates.slice(-6).reverse()
})

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: '已完成',
    in_progress: '进行中',
    pending: '等待中',
    skipped: '已跳过',
    blocked: '已阻塞',
  }
  return labels[status] || status
}

function nodeKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    goal: '目标',
    schema: '结构',
    query: '查询',
    analysis: '分析',
    knowledge: '知识',
    visualization: '可视化',
    answer: '回答',
    task: '任务',
  }
  return labels[kind] || kind
}

function eventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
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
  return labels[type] || type
}

function eventHeadline(event: AgentEvent): string {
  return (
    event.metadata?.node_title ||
    event.metadata?.tool_label ||
    event.metadata?.tool_name ||
    event.metadata?.stage_id ||
    event.content.slice(0, 24)
  )
}

function eventCopy(event: AgentEvent): string {
  return event.content.slice(0, 84)
}
</script>

<style scoped>
.workbench-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(243, 249, 255, 0.8)),
    radial-gradient(circle at top left, rgba(127, 215, 255, 0.16), transparent 30%);
  box-shadow: 0 18px 40px rgba(38, 63, 95, 0.08);
}

.workbench-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 340px;
  color: var(--ink-soft);
  font-size: 14px;
}

.placeholder-icon {
  font-size: 22px;
}

.workbench-header {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.95fr);
  gap: 14px;
}

.mode-badge,
.lane-kicker,
.filmstrip-kicker,
.signal-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.header-title {
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 28px;
  line-height: 1.05;
  letter-spacing: -0.04em;
  font-weight: 780;
}

.header-summary {
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.header-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.stat-card,
.signal-card,
.pending-card {
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 10px 20px rgba(38, 63, 95, 0.06);
}

.stat-card span,
.pending-card span {
  display: block;
  color: var(--ink-soft);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.stat-card strong,
.pending-card strong {
  display: block;
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: 20px;
  line-height: 1.2;
}

.canvas-grid {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 240px;
  gap: 14px;
  align-items: stretch;
}

.lane-card,
.focus-card,
.filmstrip {
  border-radius: 22px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(247, 251, 255, 0.82));
  box-shadow: 0 12px 28px rgba(38, 63, 95, 0.07);
}

.lane-card {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.lane-title {
  color: var(--ink-strong);
  font-size: 22px;
  letter-spacing: -0.04em;
  font-weight: 740;
}

.lane-list {
  display: grid;
  gap: 10px;
}

.lane-node {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  border-radius: 16px;
  background: rgba(248, 251, 255, 0.9);
  color: var(--ink);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.lane-node:hover,
.satellite-node:hover,
.film-card:hover {
  transform: translateY(-1px);
  border-color: rgba(79, 135, 255, 0.24);
  box-shadow: 0 12px 28px rgba(79, 135, 255, 0.1);
}

.lane-node-status {
  color: var(--accent-blue);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.lane-node strong,
.binding-line strong,
.signal-card strong,
.film-card strong,
.satellite-node strong {
  color: var(--ink-strong);
}

.lane-node span:last-child,
.binding-empty,
.signal-card p,
.film-card span:last-child {
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.6;
}

.binding-card {
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  background: rgba(241, 247, 255, 0.84);
}

.binding-label {
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.binding-mode-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.binding-mode-pill,
.focus-chip.query-analysis,
.focus-chip.query-compare,
.focus-chip.query-drilldown,
.focus-chip.query-hybrid {
  display: inline-flex;
  align-items: center;
  padding: 7px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.binding-mode-pill.mode-analysis,
.focus-chip.query-analysis {
  background: rgba(79, 135, 255, 0.08);
  color: var(--accent-blue);
}

.binding-mode-pill.mode-compare,
.focus-chip.query-compare {
  background: rgba(255, 183, 100, 0.16);
  color: #9e6414;
}

.binding-mode-pill.mode-drilldown,
.focus-chip.query-drilldown {
  background: rgba(109, 216, 194, 0.16);
  color: #1c8b76;
}

.binding-mode-pill.mode-hybrid,
.focus-chip.query-hybrid {
  background: rgba(137, 118, 255, 0.14);
  color: #5c49c8;
}

.binding-mode-copy {
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.6;
}

.binding-line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 12px;
}

.binding-line.mode-line strong {
  color: #9e6414;
}

.focus-card {
  padding: 18px;
}

.focus-shell {
  position: relative;
  overflow: hidden;
  padding: 24px;
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(247, 251, 255, 0.86)),
    radial-gradient(circle at top right, rgba(255, 183, 100, 0.18), transparent 26%);
  border: 1px solid rgba(89, 114, 145, 0.14);
}

.focus-status {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(79, 135, 255, 0.1);
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.focus-status.status-completed {
  background: rgba(109, 216, 194, 0.14);
  color: #1c8b76;
}

.focus-status.status-blocked {
  background: rgba(227, 107, 115, 0.14);
  color: var(--accent-red);
}

.focus-title {
  margin-top: 14px;
  color: var(--ink-strong);
  font-size: 36px;
  line-height: 1.02;
  letter-spacing: -0.06em;
  font-weight: 820;
}

.focus-subtitle {
  margin-top: 10px;
  color: #be7d23;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.focus-detail {
  margin-top: 14px;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.8;
}

.focus-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.focus-chip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(79, 135, 255, 0.08);
  color: var(--ink);
  font-size: 11px;
}

.focus-chip.accent {
  background: rgba(255, 183, 100, 0.16);
  color: #9e6414;
}

.signal-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.signal-card {
  min-height: 140px;
}

.signal-card strong {
  display: block;
  margin-top: 10px;
  font-size: 18px;
  line-height: 1.35;
}

.signal-card p {
  margin-top: 10px;
}

.satellite-cloud {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.satellite-node {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.satellite-node.active {
  border-color: rgba(255, 183, 100, 0.26);
  background: rgba(255, 249, 241, 0.94);
}

.satellite-kind {
  color: var(--ink-soft);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.satellite-node span:last-child {
  color: var(--ink-soft);
  font-size: 12px;
}

.filmstrip {
  padding: 18px;
}

.filmstrip-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.filmstrip-header h4 {
  margin-top: 6px;
  color: var(--ink-strong);
  font-size: 22px;
  letter-spacing: -0.04em;
  font-weight: 740;
}

.filmstrip-count {
  color: var(--ink-soft);
  font-size: 12px;
}

.filmstrip-track {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.film-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 148px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  background: rgba(247, 250, 255, 0.9);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.film-card.selected {
  border-color: rgba(79, 135, 255, 0.24);
  background: rgba(243, 249, 255, 0.98);
}

.film-type {
  color: var(--accent-blue);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

@media (max-width: 1320px) {
  .workbench-header,
  .canvas-grid,
  .filmstrip-track {
    grid-template-columns: 1fr;
  }

  .header-stats,
  .satellite-cloud {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .signal-row,
  .header-stats,
  .satellite-cloud {
    grid-template-columns: 1fr;
  }
}
</style>
