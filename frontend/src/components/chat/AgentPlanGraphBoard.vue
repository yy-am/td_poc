<template>
  <div class="plan-panel">
    <template v-if="planGraph">
      <div class="plan-header">
        <div>
          <div class="eyebrow">Agentic Plan Graph</div>
          <h3>{{ planGraph.title }}</h3>
          <p class="header-summary">{{ planGraph.summary || '模型会先规划，再沿着真实工具链路推进。' }}</p>
        </div>
        <div class="header-meta">
          <span class="meta-pill">节点 {{ graphNodes.length }}</span>
          <span class="meta-pill">模型规划</span>
          <button class="follow-btn" :class="{ active: followActive }" type="button" @click="focusActiveNode">
            {{ followActive ? '跟随活跃节点中' : '定位当前节点' }}
          </button>
        </div>
      </div>

      <div class="plan-body">
        <div class="graph-shell">
          <div class="legend">
            <span><i class="dot pending"></i>待执行</span>
            <span><i class="dot progress"></i>进行中</span>
            <span><i class="dot done"></i>已完成</span>
            <span><i class="dot blocked"></i>阻塞/跳过</span>
          </div>
          <div class="graph-scroll">
            <div ref="chartRef" class="graph-canvas" :style="{ width: `${chartWidth}px`, height: `${chartHeight}px` }"></div>
          </div>
        </div>

        <div v-if="selectedNode" class="detail-panel">
          <div class="detail-top">
            <div>
              <div class="status-chip" :class="`status-${selectedNode.node.status}`">{{ formatStatus(selectedNode.node.status) }}</div>
              <h4>{{ selectedNode.node.title }}</h4>
            </div>
            <div class="detail-meta">
              <span>{{ getKindLabel(selectedNode.node.kind) }}</span>
              <span>证据 {{ selectedNode.steps.length }} 条</span>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">步骤说明</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.node.detail)"></div>
          </div>

          <div v-if="selectedNode.node.done_when" class="detail-section">
            <div class="section-title">完成条件</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.node.done_when)"></div>
          </div>

          <div v-if="selectedNode.node.tool_hints?.length" class="detail-section">
            <div class="section-title">可能会用到的工具</div>
            <div class="hint-list">
              <span v-for="hint in selectedNode.node.tool_hints" :key="hint" class="hint-pill">{{ hint }}</span>
            </div>
          </div>

          <div v-if="selectedNode.latestThinking" class="detail-section">
            <div class="section-title">模型当前思路</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.latestThinking.content)"></div>
          </div>

          <div v-if="selectedNode.latestAction" class="detail-section">
            <div class="section-title">工具计划</div>
            <p v-if="selectedNode.latestAction.metadata?.tool_label"><strong>{{ selectedNode.latestAction.metadata.tool_label }}</strong></p>
            <div v-if="selectedNode.latestAction.metadata?.tool_summary" class="rich-text" v-html="renderRichText(selectedNode.latestAction.metadata.tool_summary)"></div>
            <div v-if="selectedNode.latestAction.metadata?.tool_input_summary" class="rich-text" v-html="renderRichText(selectedNode.latestAction.metadata.tool_input_summary)"></div>
          </div>

          <div v-if="selectedNode.latestObservation?.metadata?.sql_summary" class="detail-section">
            <div class="section-title">SQL 在做什么</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.latestObservation.metadata.sql_summary)"></div>
          </div>

          <div v-if="selectedNode.latestObservation?.metadata?.result_summary" class="detail-section">
            <div class="section-title">结果解读</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.latestObservation.metadata.result_summary)"></div>
          </div>

          <div v-if="selectedNode.tableData" class="detail-section">
            <div class="section-title">结果表格</div>
            <el-table :data="selectedNode.tableData.rows" size="small" stripe max-height="240" class="detail-table">
              <el-table-column
                v-for="col in selectedNode.tableData.columns"
                :key="col"
                :prop="col"
                :label="col"
                min-width="120"
                show-overflow-tooltip
              />
            </el-table>
          </div>

          <div v-if="selectedNode.chartConfig" class="detail-section">
            <div class="section-title">结果图表</div>
            <div class="chart-preview"><ChartRenderer :option="selectedNode.chartConfig" /></div>
          </div>

          <details v-if="selectedNode.steps.length" class="detail-section raw-panel">
            <summary>查看这个节点的原始事件</summary>
            <div class="raw-list">
              <div v-for="(step, index) in selectedNode.steps" :key="`${step.timestamp}-${index}`" class="raw-card">
                <div class="raw-head">
                  <span>{{ getStepLabel(step.type) }}</span>
                  <span>#{{ step.step_number }}</span>
                </div>
                <pre class="raw-block">{{ truncate(step.content, 2400) }}</pre>
              </div>
            </div>
          </details>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="plan-header unavailable-header">
        <div>
          <div class="eyebrow">Agentic Plan Graph</div>
          <h3>真实计划图暂未生成</h3>
          <p class="header-summary">{{ unavailableMessage }}</p>
        </div>
        <div class="header-meta">
          <span class="meta-pill">当前不展示伪计划图</span>
        </div>
      </div>
    </template>

    <div v-if="latestAnswer" class="result-board">
      <div class="board-head">
        <div>
          <div class="eyebrow">最终回答</div>
          <h4>{{ latestAnswerTitle }}</h4>
        </div>
      </div>
      <div class="board-content">
        <div class="board-text rich-text markdown" v-html="renderRichText(latestAnswer.content)"></div>
        <div v-if="latestAnswerChart" class="board-chart"><ChartRenderer :option="latestAnswerChart" /></div>
        <div v-if="latestAnswerTable" class="board-table">
          <el-table :data="latestAnswerTable.rows" size="small" stripe max-height="260" class="detail-table">
            <el-table-column
              v-for="col in latestAnswerTable.columns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </div>
    </div>

    <div v-if="isStreaming" class="streaming-indicator">
      <span></span><span></span><span></span>
      <em>模型和工具链路正在更新中</em>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { AgentStep, AgentStepType, PlanGraph, PlanGraphEdge, PlanGraphNode, PlanItemStatus } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

interface NodeView {
  node: PlanGraphNode
  steps: AgentStep[]
  latestThinking?: AgentStep
  latestAction?: AgentStep
  latestObservation?: AgentStep
  latestAnswer?: AgentStep
  chartConfig?: Record<string, any> | null
  tableData?: { columns: string[]; rows: Record<string, any>[] } | null
}

const props = defineProps<{ steps: AgentStep[]; isStreaming?: boolean }>()

const chartRef = ref<HTMLElement>()
const chartWidth = ref(980)
const chartHeight = ref(420)
const selectedNodeId = ref('')
const followActive = ref(true)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const planGraph = computed<PlanGraph | null>(() => extractRealPlanGraph(props.steps))
const hasFallbackPlan = computed(() => props.steps.some(step => {
  if (!['plan', 'plan_update', 'status'].includes(step.type)) return false
  return step.metadata?.plan_source === 'fallback' || step.metadata?.plan_graph?.source === 'fallback'
}))
const unavailableMessage = computed(() => {
  if (hasFallbackPlan.value) return '当前只有保底规划或规划超时，这不是模型真实生成的计划图，所以不会渲染成 agentic graph。'
  if (props.isStreaming) return '模型正在尝试生成真实计划图；一旦返回，会自动替换当前占位状态。'
  return '这一轮没有拿到可验证的模型计划图。'
})
const graphNodes = computed(() => planGraph.value ? buildNodeViews(planGraph.value, props.steps) : [])
const selectedNode = computed<NodeView | null>(() => {
  if (!graphNodes.value.length) return null
  const current = graphNodes.value.find(node => node.node.id === selectedNodeId.value)
  return current || graphNodes.value[0]
})
const latestAnswer = computed(() => [...props.steps].reverse().find(step => step.type === 'answer') || null)
const latestArtifactStep = computed(() => [...props.steps].reverse().find(step => step.metadata?.chart_config || step.metadata?.table_data) || null)
const latestAnswerNode = computed(() => {
  if (!latestAnswer.value) return null
  return graphNodes.value.find(node => node.latestAnswer?.timestamp === latestAnswer.value?.timestamp) || null
})
const latestAnswerTitle = computed(() => latestAnswerNode.value?.node.title || '最终回答')
const latestAnswerChart = computed(() => latestAnswerNode.value?.chartConfig || latestArtifactStep.value?.metadata?.chart_config || null)
const latestAnswerTable = computed(() => latestAnswerNode.value?.tableData || latestArtifactStep.value?.metadata?.table_data || null)

onMounted(() => {
  nextTick(() => {
    initChart()
    syncSelection()
    renderChart()
  })
})

watch(() => props.steps, async () => {
  syncSelection()
  await nextTick()
  renderChart()
}, { deep: true })

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

function extractRealPlanGraph(steps: AgentStep[]): PlanGraph | null {
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const graph = steps[index].metadata?.plan_graph
    const source = steps[index].metadata?.plan_source || graph?.source
    if (graph?.nodes?.length && source === 'llm') return graph
  }
  return null
}

function buildNodeViews(plan: PlanGraph, steps: AgentStep[]): NodeView[] {
  const views: NodeView[] = plan.nodes.map(node => ({
    node,
    steps: [],
    latestThinking: undefined,
    latestAction: undefined,
    latestObservation: undefined,
    latestAnswer: undefined,
    chartConfig: null,
    tableData: null,
  }))
  const viewMap = new Map(views.map(view => [view.node.id, view]))

  for (const step of steps) {
    const nodeId = step.metadata?.plan_node_id || inferNodeIdForStep(step, plan)
    if (!nodeId) continue
    const view = viewMap.get(nodeId)
    if (!view) continue

    view.steps.push(step)
    if (step.type === 'thinking') view.latestThinking = step
    if (step.type === 'action') view.latestAction = step
    if (step.type === 'observation') {
      view.latestObservation = step
      if (step.metadata?.chart_config) view.chartConfig = step.metadata.chart_config
      if (step.metadata?.table_data) view.tableData = step.metadata.table_data
    }
    if (step.type === 'answer') view.latestAnswer = step
  }

  return views
}

function inferNodeIdForStep(step: AgentStep, plan: PlanGraph): string | null {
  const activeIds = plan.active_node_ids || []
  if (step.type === 'plan' || step.type === 'plan_update') return activeIds[0] || plan.nodes[0]?.id || null
  return activeIds[0] || plan.nodes[0]?.id || null
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  chart.on('click', { dataType: 'node' }, params => {
    const nodeId = String((params.data as any)?.id || '')
    if (!nodeId) return
    selectedNodeId.value = nodeId
    followActive.value = false
    renderChart()
  })
  resizeObserver = new ResizeObserver(() => renderChart())
  if (chartRef.value.parentElement) {
    resizeObserver.observe(chartRef.value.parentElement)
  }
}

function syncSelection() {
  if (!graphNodes.value.length) {
    selectedNodeId.value = ''
    return
  }
  const currentPlan = planGraph.value
  if (followActive.value) {
    selectedNodeId.value = currentPlan?.active_node_ids?.[0] || graphNodes.value[graphNodes.value.length - 1].node.id
  } else if (!graphNodes.value.some(node => node.node.id === selectedNodeId.value)) {
    selectedNodeId.value = graphNodes.value[0].node.id
  }
}

function focusActiveNode() {
  followActive.value = true
  syncSelection()
  renderChart()
}

function renderChart() {
  if (!chart || !chartRef.value) return
  const currentPlan = planGraph.value
  if (!currentPlan) {
    chart.clear()
    return
  }

  const layout = buildLayout(currentPlan)
  chartWidth.value = layout.width
  chartHeight.value = layout.height

  const seriesData = graphNodes.value.map(view => {
    const point = layout.points.get(view.node.id) || { x: 120, y: 120 }
    const active = view.node.id === selectedNodeId.value
    const current = (currentPlan.active_node_ids || []).includes(view.node.id)
    return {
      id: view.node.id,
      name: view.node.title,
      x: point.x,
      y: point.y,
      symbolSize: active ? 82 : current ? 74 : 64,
      itemStyle: {
        color: getNodeColor(view.node.status, active || current),
        borderColor: active ? '#f5fbff' : 'rgba(255,255,255,0.18)',
        borderWidth: active ? 3 : 1,
        shadowBlur: active ? 26 : 12,
        shadowColor: getNodeColor(view.node.status, true),
      },
      label: {
        show: true,
        formatter: wrapLabel(view.node.title, 10),
        color: '#eef4ff',
        fontSize: 12,
        fontWeight: 700,
        lineHeight: 16,
      },
    }
  })

  const edges = (currentPlan.edges?.length ? currentPlan.edges : buildFallbackEdges(currentPlan.nodes)).map(edge => ({
    source: edge.source,
    target: edge.target,
    lineStyle: { color: 'rgba(152, 175, 220, 0.42)', width: 2, curveness: 0.06 },
    symbol: ['none', 'arrow'],
    symbolSize: 10,
  }))

  chart.setOption({
    animationDurationUpdate: 260,
    xAxis: { show: false, min: 0, max: chartWidth.value },
    yAxis: { show: false, min: 0, max: chartHeight.value },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(10, 18, 33, 0.96)',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: { color: '#eef3ff' },
      formatter: (params: any) => {
        if (params.dataType !== 'node') return ''
        const node = graphNodes.value.find(item => item.node.id === params.data.id)
        if (!node) return ''
        return `<div style="min-width:240px"><div style="font-weight:700;margin-bottom:6px">${escapeHtml(node.node.title)}</div><div style="color:#9fb7e7;font-size:12px">${escapeHtml(formatStatus(node.node.status))} · ${escapeHtml(getKindLabel(node.node.kind))}</div><div style="margin-top:8px;line-height:1.6">${escapeHtml(truncate(node.node.detail, 160))}</div></div>`
      },
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: false,
      data: seriesData,
      edges,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 10,
      emphasis: { scale: false },
    }],
  }, true)

  chart.resize({ width: chartWidth.value, height: chartHeight.value })
}

function buildLayout(plan: PlanGraph) {
  const edges = plan.edges?.length ? plan.edges : buildFallbackEdges(plan.nodes)
  const incoming = new Map<string, number>()
  const outgoing = new Map<string, string[]>()
  for (const node of plan.nodes) {
    incoming.set(node.id, 0)
    outgoing.set(node.id, [])
  }
  for (const edge of edges) {
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1)
    outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge.target])
  }

  const levelMap = new Map<string, number>()
  const queue = plan.nodes.filter(node => (incoming.get(node.id) || 0) === 0).map(node => node.id)
  for (const nodeId of queue) levelMap.set(nodeId, 0)
  while (queue.length) {
    const source = queue.shift() as string
    const currentLevel = levelMap.get(source) || 0
    for (const target of outgoing.get(source) || []) {
      const nextLevel = Math.max(levelMap.get(target) || 0, currentLevel + 1)
      levelMap.set(target, nextLevel)
      incoming.set(target, (incoming.get(target) || 1) - 1)
      if ((incoming.get(target) || 0) <= 0) queue.push(target)
    }
  }
  for (const node of plan.nodes) if (!levelMap.has(node.id)) levelMap.set(node.id, 0)

  const byLevel = new Map<number, PlanGraphNode[]>()
  for (const node of plan.nodes) {
    const level = levelMap.get(node.id) || 0
    byLevel.set(level, [...(byLevel.get(level) || []), node])
  }

  const maxLevel = Math.max(0, ...Array.from(byLevel.keys()))
  const width = Math.max(980, (maxLevel + 1) * 240 + 180)
  const maxRows = Math.max(...Array.from(byLevel.values()).map(nodes => nodes.length), 1)
  const height = Math.max(420, maxRows * 150 + 120)
  const points = new Map<string, { x: number; y: number }>()

  Array.from(byLevel.entries()).sort((a, b) => a[0] - b[0]).forEach(([level, nodes]) => {
    nodes.forEach((node, index) => {
      const spacing = height / (nodes.length + 1)
      points.set(node.id, {
        x: 120 + level * 220,
        y: Math.round(spacing * (index + 1)),
      })
    })
  })

  return { points, width, height }
}

function buildFallbackEdges(nodes: PlanGraphNode[] | undefined): PlanGraphEdge[] {
  if (!nodes?.length) return []
  return nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id }))
}

function getNodeColor(status: PlanItemStatus, active = false): string {
  const palette: Record<PlanItemStatus, string> = {
    pending: active ? '#70b6ff' : '#4379b9',
    in_progress: active ? '#8dc1ff' : '#4e90de',
    completed: active ? '#7dde91' : '#4da565',
    skipped: active ? '#cbb4ff' : '#8970b8',
    blocked: active ? '#ff9b9b' : '#c15b5b',
  }
  return palette[status]
}

function formatStatus(status: PlanItemStatus) {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '进行中'
    case 'skipped': return '已跳过'
    case 'blocked': return '已阻塞'
    default: return '待执行'
  }
}

function getKindLabel(kind: PlanGraphNode['kind']) {
  return {
    goal: '目标澄清',
    schema: '结构核对',
    query: '取数查询',
    analysis: '分析整理',
    knowledge: '规则核对',
    visualization: '图表生成',
    answer: '结果交付',
    task: '执行任务',
  }[kind]
}

function getStepLabel(type: AgentStepType) {
  return {
    plan: '计划',
    plan_update: '计划更新',
    thinking: '思考',
    action: '行动',
    observation: '观察',
    answer: '回答',
    chart: '图表',
    table: '表格',
    error: '异常',
    status: '状态',
    agent_start: '开始',
    review: '审查',
    replan_trigger: '重规划',
  }[type]
}

function fallbackTitle(step: AgentStep) {
  if (step.type === 'thinking') return '模型思考'
  if (step.type === 'action') return step.metadata?.tool_label || '工具执行'
  if (step.type === 'answer') return '最终回答'
  if (step.type === 'error') return '执行异常'
  return '执行步骤'
}

function legacyKind(type: AgentStepType): PlanGraphNode['kind'] {
  if (type === 'answer') return 'answer'
  if (type === 'thinking') return 'analysis'
  if (type === 'action' || type === 'observation') return 'query'
  return 'task'
}

void fallbackTitle
void legacyKind

void [fallbackTitle, legacyKind]

function wrapLabel(text: string, maxChars: number) {
  const compact = text.replace(/\s+/g, '')
  if (compact.length <= maxChars) return compact
  const rows: string[] = []
  for (let index = 0; index < compact.length; index += maxChars) rows.push(compact.slice(index, index + maxChars))
  return rows.slice(0, 3).join('\n')
}

function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function escapeHtml(text: string) {
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
}

function renderRichText(text: string) {
  const source = escapeHtml((text || '').replace(/\r\n/g, '\n').trim())
  if (!source) return ''
  return source.split(/\n{2,}/).map(renderBlock).join('')
}

function renderBlock(block: string) {
  const lines = block.split('\n').map(line => line.trimEnd()).filter(Boolean)
  if (!lines.length) return ''
  if (lines.every(line => /^[-*]\s+/.test(line))) return `<ul>${lines.map(line => `<li>${renderInline(line.replace(/^[-*]\s+/, ''))}</li>`).join('')}</ul>`
  if (lines.every(line => /^\d+\.\s+/.test(line))) return `<ol>${lines.map(line => `<li>${renderInline(line.replace(/^\d+\.\s+/, ''))}</li>`).join('')}</ol>`
  if (lines.every(line => /^#{1,3}\s+/.test(line))) {
    return lines.map(line => {
      const level = Math.min(3, line.match(/^#+/)?.[0].length || 1)
      return `<h${level}>${renderInline(line.replace(/^#{1,3}\s+/, ''))}</h${level}>`
    }).join('')
  }
  return `<p>${lines.map(renderInline).join('<br>')}</p>`
}

function renderInline(text: string) {
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>')
}
</script>

<style scoped>
.plan-panel{background:radial-gradient(circle at top left,rgba(84,199,255,.12),transparent 35%),linear-gradient(145deg,#131d31,#0f1627);border:1px solid rgba(255,255,255,.08);border-radius:24px;padding:18px}
.plan-header{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:16px}
.eyebrow{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#88c9ff;margin-bottom:4px}
.plan-header h3,.board-head h4,.detail-top h4{margin:0;color:#f2f6ff;font-size:20px}
.header-summary{margin:8px 0 0;color:#c6d4ef;line-height:1.7;font-size:14px;max-width:720px}
.header-meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.meta-pill,.follow-btn,.hint-pill,.status-chip{border-radius:999px;padding:8px 12px;font-size:12px}
.meta-pill,.hint-pill{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);color:#cfdcf5}
.follow-btn{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#d7e4ff;cursor:pointer}
.follow-btn.active{background:rgba(84,199,255,.16);border-color:rgba(84,199,255,.3);color:#f2f8ff}
.plan-body{display:grid;grid-template-columns:minmax(0,1.22fr) minmax(340px,.94fr);gap:16px;min-height:520px}
.graph-shell,.detail-panel,.result-board{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:20px}
.graph-shell{padding:14px}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:#b8c7e6;font-size:12px;margin-bottom:10px}
.dot{display:inline-block;width:10px;height:10px;border-radius:999px;margin-right:6px}
.dot.pending{background:#4e90de}.dot.progress{background:#8dc1ff}.dot.done{background:#4da565}.dot.blocked{background:#c15b5b}
.graph-scroll{overflow:auto}
.graph-canvas{min-height:420px}
.detail-panel{padding:16px;overflow-y:auto;max-height:560px}
.detail-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}
.detail-meta{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;color:#98a9c9;font-size:12px}
.status-chip{display:inline-flex;margin-bottom:8px;background:rgba(84,199,255,.16);color:#9fd7ff}
.status-completed{background:rgba(103,194,58,.16);color:#b7f59c}.status-in_progress{background:rgba(64,158,255,.16);color:#9fd7ff}.status-skipped{background:rgba(146,137,199,.2);color:#d0c8ff}.status-blocked{background:rgba(245,108,108,.16);color:#ffb0b0}.status-pending{background:rgba(125,135,156,.2);color:#d6dded}
.detail-section{margin-top:14px}
.section-title{color:#9fd7ff;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.hint-list{display:flex;flex-wrap:wrap;gap:8px}
.detail-table :deep(.el-table__header){background:rgba(7,13,24,.96)}
.detail-table :deep(.el-table__body tr){background:rgba(16,25,42,.92)}
.chart-preview,.board-chart{border-radius:16px;overflow:hidden;background:rgba(7,13,24,.88);padding:10px}
.raw-panel summary{cursor:pointer;color:#c7d5ef}
.raw-list{display:grid;gap:10px;margin-top:10px}
.raw-card{border-radius:14px;padding:10px 12px;background:rgba(255,255,255,.04)}
.raw-head{display:flex;align-items:center;justify-content:space-between;color:#a9bad8;font-size:12px;margin-bottom:8px}
.raw-block{display:block;margin:0;border-radius:14px;padding:12px 14px;background:rgba(7,13,24,.88);color:#dbe5f8;font-size:12px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.result-board{margin-top:16px;padding:16px}
.board-content{display:grid;gap:14px}
.board-text{color:#e4ebf9;line-height:1.85;font-size:14px}
.streaming-indicator{display:inline-flex;align-items:center;gap:10px;margin-top:14px;color:#a9bad8;font-size:12px}
.streaming-indicator span{width:7px;height:7px;border-radius:50%;background:#54c7ff;animation:bounce 1.2s ease-in-out infinite}
.streaming-indicator span:nth-child(2){animation-delay:.16s}.streaming-indicator span:nth-child(3){animation-delay:.32s}
.rich-text :deep(p),.rich-text :deep(ul),.rich-text :deep(ol),.rich-text :deep(h1),.rich-text :deep(h2),.rich-text :deep(h3){margin:0 0 10px}
.rich-text :deep(ul),.rich-text :deep(ol){padding-left:20px}
.rich-text :deep(li){margin-bottom:6px}
.rich-text :deep(strong){color:#f4f8ff;font-weight:700}
.rich-text :deep(code){display:inline-block;padding:2px 6px;border-radius:6px;background:rgba(7,13,24,.88);color:#a7d0ff}
.markdown{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);border-radius:14px;padding:12px 14px}
@keyframes bounce{0%,80%,100%{transform:translateY(0);opacity:.35}40%{transform:translateY(-4px);opacity:1}}
@media (max-width:1200px){.plan-header{flex-direction:column}.plan-body{grid-template-columns:1fr}.header-meta{justify-content:flex-start}.detail-panel{max-height:none}}
</style>
