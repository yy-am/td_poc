<template>
  <div class="react-panel">
    <div class="react-header">
      <div>
        <div class="eyebrow">ReAct 实时图谱</div>
        <h3>基于真实 WebSocket 事件压缩展示</h3>
      </div>
      <div class="header-meta">
        <span class="meta-pill">原始事件 {{ steps.length }}</span>
        <span class="meta-pill">关键节点 {{ visualNodes.length }}</span>
        <button class="follow-btn" :class="{ active: followLatest }" type="button" @click="enableFollowLatest">
          {{ followLatest ? '跟随最新中' : '切回最新节点' }}
        </button>
      </div>
    </div>

    <div class="react-body">
      <div class="graph-shell">
        <div class="lane-legend">
          <span><i class="dot lane-plan"></i>计划</span>
          <span><i class="dot lane-think"></i>思考</span>
          <span><i class="dot lane-act"></i>执行</span>
          <span><i class="dot lane-result"></i>结果</span>
        </div>
        <div class="graph-scroll">
          <div ref="chartRef" class="graph-canvas" :style="{ width: `${chartWidth}px` }"></div>
        </div>
      </div>

      <div v-if="selectedNode" class="detail-panel">
        <div class="detail-top">
          <div>
            <div class="detail-chip">{{ getNodeCategory(selectedNode.kind) }}</div>
            <h4>{{ selectedNode.title }}</h4>
          </div>
          <div class="detail-meta">
            <span v-if="selectedNode.primaryStep.metadata?.duration_ms">{{ selectedNode.primaryStep.metadata.duration_ms }}ms</span>
            <span>原始事件 {{ selectedNode.rawSteps.length }} 条</span>
          </div>
        </div>

        <div class="detail-summary rich-text" :class="{ markdown: isMarkdownLike(selectedNode.summary) }" v-html="renderRichText(selectedNode.summary)"></div>

        <template v-if="selectedNode.kind === 'plan'">
          <div class="detail-section">
            <div class="section-title">当前计划</div>
            <div class="plan-list">
              <div v-for="item in selectedNode.primaryStep.metadata?.plan_items || []" :key="item.key" class="plan-item">
                <div class="plan-head">
                  <span class="mini-dot" :class="`dot-${item.status}`"></span>
                  <span class="plan-title">{{ item.title }}</span>
                  <span class="plan-status">{{ formatPlanStatus(item.status) }}</span>
                </div>
                <p>{{ item.detail }}</p>
              </div>
            </div>
          </div>
          <div v-if="selectedNode.primaryStep.metadata?.change_reason" class="detail-section">
            <div class="section-title">最近一次计划更新原因</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.primaryStep.metadata.change_reason)"></div>
          </div>
        </template>

        <template v-else>
          <div v-if="selectedNode.toolLabel || selectedNode.toolSummary || selectedNode.toolInputSummary" class="detail-section">
            <div class="section-title">工具说明</div>
            <p v-if="selectedNode.toolLabel"><strong>{{ selectedNode.toolLabel }}</strong></p>
            <div v-if="selectedNode.toolSummary" class="rich-text" v-html="renderRichText(selectedNode.toolSummary)"></div>
            <div v-if="selectedNode.toolInputSummary" class="rich-text" v-html="renderRichText(selectedNode.toolInputSummary)"></div>
          </div>
          <div v-if="selectedNode.sqlSummary" class="detail-section">
            <div class="section-title">SQL 在做什么</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.sqlSummary)"></div>
          </div>
          <div v-if="selectedNode.resultSummary" class="detail-section">
            <div class="section-title">结果解读</div>
            <div class="rich-text" v-html="renderRichText(selectedNode.resultSummary)"></div>
          </div>
          <div v-if="selectedNode.artifactTable" class="detail-section">
            <div class="section-title">结果表格</div>
            <el-table :data="selectedNode.artifactTable.rows" size="small" stripe max-height="240" class="detail-table">
              <el-table-column v-for="col in selectedNode.artifactTable.columns" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
            </el-table>
          </div>
          <div v-if="selectedNode.artifactChart" class="detail-section">
            <div class="section-title">结果图表</div>
            <div class="chart-preview"><ChartRenderer :option="selectedNode.artifactChart" /></div>
          </div>
          <details v-if="selectedNodeHasRawDetails" class="detail-section raw-panel">
            <summary>查看原始事件内容</summary>
            <div class="raw-events">
              <div v-for="(rawStep, index) in selectedNode.rawSteps" :key="`${rawStep.timestamp}-${index}`" class="raw-event-card">
                <div class="raw-event-head">
                  <span>{{ getStepCategory(rawStep.type) }}</span>
                  <span>#{{ rawStep.step_number }}</span>
                </div>
                <pre v-if="rawStep.metadata?.tool_input" class="raw-block">{{ formatJSON(rawStep.metadata.tool_input) }}</pre>
                <code v-if="rawStep.metadata?.sql_preview" class="raw-block code-block">{{ rawStep.metadata.sql_preview }}</code>
                <code v-if="rawStep.metadata?.sql" class="raw-block code-block">{{ rawStep.metadata.sql }}</code>
                <pre v-if="rawStep.content" class="raw-block">{{ truncate(rawStep.content, 2400) }}</pre>
              </div>
            </div>
          </details>
        </template>
      </div>
    </div>

    <div v-if="latestResultNode" class="result-board">
      <div class="board-head">
        <div>
          <div class="eyebrow">最终结果区</div>
          <h4>{{ latestResultNode.title }}</h4>
        </div>
      </div>
      <div class="board-content">
        <div class="board-text rich-text" :class="{ markdown: isMarkdownLike(latestResultNode.summary) }" v-html="renderRichText(latestResultNode.summary)"></div>
        <div v-if="latestResultNode.artifactChart" class="board-chart"><ChartRenderer :option="latestResultNode.artifactChart" /></div>
        <div v-if="latestResultNode.artifactTable" class="board-table">
          <el-table :data="latestResultNode.artifactTable.rows" size="small" stripe max-height="260" class="detail-table">
            <el-table-column v-for="col in latestResultNode.artifactTable.columns" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
          </el-table>
        </div>
      </div>
    </div>

    <div v-if="isStreaming" class="streaming-indicator">
      <span></span><span></span><span></span>
      <em>模型和工具链路正在实时更新</em>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { AgentStep, AgentStepType, PlanItemStatus } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

type VisualNodeKind = 'plan' | 'thinking' | 'execution' | 'answer' | 'error'
type Intent = 'schema' | 'chart' | 'knowledge' | 'analysis' | 'query'

interface VisualNode {
  id: string
  kind: VisualNodeKind
  title: string
  summary: string
  primaryStep: AgentStep
  rawSteps: AgentStep[]
  toolLabel?: string
  toolSummary?: string
  toolInputSummary?: string
  sqlSummary?: string
  resultSummary?: string
  artifactChart?: Record<string, any> | null
  artifactTable?: { columns: string[]; rows: Record<string, any>[] } | null
}

interface ContextProfile {
  subject?: string
  intent: Intent
}

const props = defineProps<{ steps: AgentStep[]; isStreaming?: boolean }>()
const chartRef = ref<HTMLElement>()
const selectedIndex = ref(-1)
const followLatest = ref(true)
const chartWidth = ref(960)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const visualNodes = computed(() => buildVisualNodes(props.steps))
const selectedNode = computed<VisualNode | null>(() => {
  if (!visualNodes.value.length) return null
  const idx = selectedIndex.value >= 0 ? selectedIndex.value : visualNodes.value.length - 1
  return visualNodes.value[Math.min(idx, visualNodes.value.length - 1)] || null
})
const latestResultNode = computed<VisualNode | null>(() => {
  for (let idx = visualNodes.value.length - 1; idx >= 0; idx -= 1) {
    const node = visualNodes.value[idx]
    if ((node.kind === 'answer' || node.kind === 'execution') && (node.artifactChart || node.artifactTable || node.kind === 'answer')) return node
  }
  return null
})
const selectedNodeHasRawDetails = computed(() => {
  if (!selectedNode.value) return false
  return selectedNode.value.rawSteps.some(step => Boolean(step.metadata?.tool_input || step.metadata?.sql_preview || step.metadata?.sql || step.content))
})

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

function buildVisualNodes(steps: AgentStep[]): VisualNode[] {
  const nodes: VisualNode[] = []
  const context = detectContextProfile(steps)
  const latestPlanStep = [...steps].reverse().find(step => step.type === 'plan_update' || step.type === 'plan')

  if (latestPlanStep) {
    nodes.push({
      id: `plan-${latestPlanStep.timestamp}`,
      kind: 'plan',
      title: buildPlanTitle(latestPlanStep, context),
      summary: latestPlanStep.metadata?.change_reason || latestPlanStep.content,
      primaryStep: latestPlanStep,
      rawSteps: steps.filter(step => step.type === 'plan' || step.type === 'plan_update'),
    })
  }

  let latestChart: Record<string, any> | null = null
  let latestTable: { columns: string[]; rows: Record<string, any>[] } | null = null

  for (let index = 0; index < steps.length; index += 1) {
    const step = steps[index]
    if (step.metadata?.chart_config) latestChart = step.metadata.chart_config
    if (step.metadata?.table_data) latestTable = step.metadata.table_data

    if (step.type === 'thinking') {
      const nextAction = findNextAction(steps, index + 1)
      nodes.push({
        id: `thinking-${step.timestamp}`,
        kind: 'thinking',
        title: buildThinkingTitle(context, nextAction),
        summary: step.content,
        primaryStep: step,
        rawSteps: [step],
      })
      continue
    }

    if (step.type === 'action') {
      const observation = steps[index + 1]?.type === 'observation' ? steps[index + 1] : null
      if (observation?.metadata?.chart_config) latestChart = observation.metadata.chart_config
      if (observation?.metadata?.table_data) latestTable = observation.metadata.table_data
      const title = buildExecutionTitle(step, observation, context)

      nodes.push({
        id: `execution-${step.timestamp}`,
        kind: 'execution',
        title,
        summary: step.metadata?.tool_input_summary || step.content,
        primaryStep: step,
        rawSteps: observation ? [step, observation] : [step],
        toolLabel: title,
        toolSummary: step.metadata?.tool_summary,
        toolInputSummary: step.metadata?.tool_input_summary,
        sqlSummary: step.metadata?.sql_summary || observation?.metadata?.sql_summary,
        resultSummary: observation?.metadata?.result_summary,
        artifactChart: observation?.metadata?.chart_config || null,
        artifactTable: observation?.metadata?.table_data || null,
      })

      if (observation) index += 1
      continue
    }

    if (step.type === 'answer') {
      nodes.push({
        id: `answer-${step.timestamp}`,
        kind: 'answer',
        title: buildAnswerTitle(context),
        summary: step.content,
        primaryStep: step,
        rawSteps: [step],
        artifactChart: latestChart,
        artifactTable: latestTable,
      })
      continue
    }

    if (step.type === 'error') {
      nodes.push({
        id: `error-${step.timestamp}`,
        kind: 'error',
        title: '执行异常',
        summary: step.content,
        primaryStep: step,
        rawSteps: [step],
      })
    }
  }

  return nodes
}

function detectContextProfile(steps: AgentStep[]): ContextProfile {
  const subject = [...steps].reverse().map(step => step.metadata?.semantic_subject || step.metadata?.semantic_context?.semantic_subject).find(Boolean) || inferSubject(steps)
  const intent = [...steps].reverse().map(step => step.metadata?.semantic_mode || step.metadata?.semantic_context?.request_mode).find(Boolean) as Intent | undefined
  return { subject: subject || undefined, intent: intent || inferIntent(steps) }
}

function inferSubject(steps: AgentStep[]): string {
  const text = steps.flatMap(step => [
    step.content,
    step.metadata?.tool_label,
    step.metadata?.tool_summary,
    step.metadata?.tool_input_summary,
    step.metadata?.result_summary,
    step.metadata?.sql_summary,
    step.metadata?.sql_preview,
    step.metadata?.sql,
    typeof step.metadata?.tool_input?.table_name === 'string' ? step.metadata.tool_input.table_name : '',
    typeof step.metadata?.tool_input?.query === 'string' ? step.metadata.tool_input.query : '',
  ]).filter(Boolean).join(' ').toLowerCase()

  const hasTax = /tax|vat|invoice|declaration|税务|申报|纳税|税负|发票|进项|销项/.test(text)
  const hasAccounting = /acct|account|ledger|journal|voucher|balance|trial_balance|gl_|账务|会计|账面|科目|凭证|总账|分录/.test(text)
  const hasRecon = /recon|match|diff|difference|compare|对账|差异|比对/.test(text)
  const hasRisk = /risk|warning|alert|预警|风险/.test(text)
  const hasEnterprise = /enterprise|company|taxpayer|corp|企业|纳税人|客户/.test(text)

  if (hasTax && hasAccounting) return '税账差异'
  if (hasRecon) return '对账'
  if (hasRisk) return '风险'
  if (hasTax) return '税务'
  if (hasAccounting) return '账务'
  if (hasEnterprise) return '企业'
  return '业务'
}

function inferIntent(steps: AgentStep[]): Intent {
  const text = steps.flatMap(step => [step.content, step.metadata?.tool_label, step.metadata?.tool_summary, step.metadata?.tool_input_summary, step.metadata?.sql_summary]).filter(Boolean).join(' ').toLowerCase()
  if (/schema|字段|结构|元数据|表结构|哪些表|columns/.test(text)) return 'schema'
  if (/图表|图|可视化|柱状|折线|饼图|趋势|占比/.test(text)) return 'chart'
  if (/规则|口径|知识|依据|knowledge/.test(text)) return 'knowledge'
  if (/分析|差异|异常|原因|对比|结论|报表/.test(text)) return 'analysis'
  return 'query'
}

function buildPlanTitle(step: AgentStep, context: ContextProfile): string {
  if (step.metadata?.plan_title && !/本轮执行计划|执行计划已更新/.test(step.metadata.plan_title)) return step.metadata.plan_title
  if (context.intent === 'schema') return context.subject === '业务' ? '表结构核对计划' : `${context.subject}结构核对计划`
  if (context.intent === 'chart') return context.subject === '业务' ? '图表分析计划' : `${context.subject}图表分析计划`
  if (context.intent === 'knowledge') return context.subject === '业务' ? '规则核对计划' : `${context.subject}规则核对计划`
  return context.subject === '业务' ? '数据分析计划' : `${context.subject}分析计划`
}

function buildThinkingTitle(context: ContextProfile, nextAction: AgentStep | null): string {
  if (!nextAction) return context.subject === '业务' ? '判断执行路径' : `判断${context.subject}处理路径`
  const title = buildExecutionTitle(nextAction, null, context)
  if (title.startsWith('查看')) return title.replace(/^查看/, '判断')
  if (title.startsWith('查询')) return title.replace(/^查询/, '规划')
  if (title.startsWith('汇总')) return title.replace(/^汇总/, '规划')
  if (title.startsWith('生成')) return title.replace(/^生成/, '规划')
  if (title.startsWith('检索')) return title.replace(/^检索/, '判断')
  if (title.startsWith('分析')) return title.replace(/^分析/, '规划')
  return `规划${title}`
}

function buildExecutionTitle(step: AgentStep, observation: AgentStep | null, context: ContextProfile): string {
  const toolName = step.metadata?.tool_name
  const subject = step.metadata?.semantic_subject || observation?.metadata?.semantic_subject || context.subject || '业务'
  const intent = (step.metadata?.semantic_mode as Intent | undefined) || context.intent
  const sql = String(step.metadata?.sql_preview || step.metadata?.tool_input?.query || observation?.metadata?.sql || '')

  if (toolName === 'metadata_query' || intent === 'schema') {
    const tableName = String(step.metadata?.tool_input?.table_name || '')
    if (!tableName) return '查看表清单'
    if (subject === '企业') return '查看企业主数据结构'
    return subject === '业务' ? '查看表结构' : `查看${subject}表结构`
  }

  if (toolName === 'chart_generator' || intent === 'chart') {
    const chartLabel = translateChartType(String(step.metadata?.tool_input?.chart_type || ''))
    return subject === '业务' ? `生成${chartLabel}` : `生成${subject}${chartLabel}`
  }

  if (toolName === 'knowledge_search' || intent === 'knowledge') {
    return subject === '业务' ? '检索业务规则' : `检索${subject}规则`
  }

  const sqlIntent = inferSqlIntent(sql)
  if (subject === '税账差异') {
    if (sqlIntent === 'ranking') return '查看税账差异排行'
    if (sqlIntent === 'aggregate') return '汇总税账差异'
    return '查询税账差异明细'
  }
  if (subject === '对账') {
    if (sqlIntent === 'ranking') return '查看对账排行'
    if (sqlIntent === 'aggregate') return '汇总对账差异'
    return '查询对账结果'
  }
  if (subject === '风险') {
    return sqlIntent === 'detail' ? '查看风险指标' : '分析风险指标'
  }
  if (sqlIntent === 'ranking') return subject === '业务' ? '查看数据排行' : `查看${subject}排行`
  if (sqlIntent === 'aggregate') return subject === '业务' ? '汇总业务数据' : `汇总${subject}数据`
  return subject === '业务' ? '查询业务数据' : `查询${subject}数据`
}

function buildAnswerTitle(context: ContextProfile): string {
  if (context.intent === 'schema') return context.subject === '业务' ? '结构查看结果' : `${context.subject}结构结论`
  if (context.intent === 'knowledge') return context.subject === '业务' ? '规则结论' : `${context.subject}规则结论`
  return context.subject === '业务' ? '最终回答' : `${context.subject}分析结论`
}

function translateChartType(chartType: string): string {
  const normalized = chartType.toLowerCase()
  if (normalized === 'line') return '趋势图'
  if (normalized === 'pie') return '占比图'
  if (normalized === 'bar') return '柱状图'
  if (normalized === 'scatter') return '散点图'
  return '图表'
}

function inferSqlIntent(sql: string): 'aggregate' | 'ranking' | 'detail' {
  const upper = sql.toUpperCase()
  if (upper.includes('ORDER BY') && upper.includes('LIMIT')) return 'ranking'
  if (upper.includes('GROUP BY') || /(SUM|AVG|COUNT|MAX|MIN)\s*\(/.test(upper)) return 'aggregate'
  return 'detail'
}

function findNextAction(steps: AgentStep[], startIndex: number): AgentStep | null {
  for (let index = startIndex; index < steps.length; index += 1) if (steps[index].type === 'action') return steps[index]
  return null
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  chart.on('click', { dataType: 'node' }, params => {
    const nodeIndex = typeof params.dataIndex === 'number' ? params.dataIndex : -1
    if (nodeIndex >= 0) {
      followLatest.value = false
      selectedIndex.value = nodeIndex
      renderChart()
    }
  })
  resizeObserver = new ResizeObserver(() => renderChart())
  resizeObserver.observe(chartRef.value.parentElement as Element)
}

function syncSelection() {
  if (!visualNodes.value.length) {
    selectedIndex.value = -1
    return
  }
  if (followLatest.value || selectedIndex.value >= visualNodes.value.length) selectedIndex.value = visualNodes.value.length - 1
}

function enableFollowLatest() {
  followLatest.value = true
  selectedIndex.value = visualNodes.value.length - 1
  renderChart()
}

function renderChart() {
  if (!chart || !chartRef.value) return
  const containerWidth = chartRef.value.parentElement?.clientWidth || 960
  chartWidth.value = Math.max(containerWidth, visualNodes.value.length * 180 + 180)

  nextTick(() => {
    if (!chart) return
    const laneY: Record<VisualNodeKind, number> = { plan: 85, thinking: 210, execution: 320, answer: 435, error: 435 }
    const nodes = visualNodes.value.map((node, index) => {
      const active = index === selectedIndex.value
      return {
        x: 110 + index * 170,
        y: laneY[node.kind],
        symbolSize: active ? 74 : 58,
        itemStyle: {
          color: getNodeColor(node.kind, active),
          borderColor: active ? '#f7fbff' : 'rgba(255,255,255,0.22)',
          borderWidth: active ? 3 : 1,
          shadowBlur: active ? 24 : 10,
          shadowColor: getNodeColor(node.kind, true),
        },
        label: {
          show: true,
          formatter: () => `${index + 1}\n${wrapLabel(node.title, 8)}`,
          color: '#f4f7ff',
          fontSize: 11,
          lineHeight: 14,
          fontWeight: 700,
        },
      }
    })
    const edges = visualNodes.value.slice(1).map((_, index) => ({
      source: index,
      target: index + 1,
      lineStyle: { color: 'rgba(143, 170, 220, 0.42)', width: 2, curveness: 0.1 },
      symbol: ['none', 'arrow'],
      symbolSize: 10,
    }))

    chart.setOption({
      animationDurationUpdate: 260,
      xAxis: { show: false, min: 0, max: chartWidth.value },
      yAxis: { show: false, min: 0, max: 500 },
      graphic: [laneText('计划', 26, 85), laneText('思考', 26, 210), laneText('执行', 26, 320), laneText('结果', 26, 435), laneDivider(135), laneDivider(260), laneDivider(380)],
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(10, 18, 33, 0.96)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: { color: '#eef3ff' },
        formatter: (params: any) => {
          if (params.dataType !== 'node') return ''
          const node = visualNodes.value[params.dataIndex]
          return `<div style="min-width:220px"><div style="font-weight:700;margin-bottom:6px">${escapeHtml(node.title)}</div><div style="color:#9fb7e7;font-size:12px">${escapeHtml(getNodeCategory(node.kind))}</div><div style="margin-top:8px;line-height:1.6">${escapeHtml(truncate(node.summary, 140))}</div></div>`
        },
      },
      series: [{ type: 'graph', layout: 'none', roam: false, data: nodes, edges, edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 10, emphasis: { scale: false } }],
    }, true)

    chart.resize({ width: chartWidth.value, height: 500 })
  })
}

function laneText(label: string, x: number, y: number) {
  return { type: 'text', left: x, top: y - 12, style: { text: label, fill: 'rgba(188, 203, 231, 0.72)', font: '12px sans-serif' }, silent: true }
}

function laneDivider(y: number) {
  return { type: 'line', left: 0, top: y, shape: { x1: 0, y1: 0, x2: chartWidth.value, y2: 0 }, style: { stroke: 'rgba(255,255,255,0.08)', lineWidth: 1 }, silent: true }
}

function wrapLabel(text: string, maxChars: number): string {
  const compact = text.replace(/\s+/g, '')
  if (compact.length <= maxChars) return compact
  const first = Math.ceil(maxChars / 2)
  return `${compact.slice(0, first)}\n${compact.slice(first, maxChars)}`
}

function getNodeCategory(kind: VisualNodeKind): string {
  return { plan: '执行计划', thinking: '模型思考', execution: '工具执行', answer: '最终回答', error: '异常' }[kind]
}

function getStepCategory(type: AgentStepType): string {
  return { plan: '计划', plan_update: '计划更新', thinking: '思考', action: '行动', observation: '观察', answer: '回答', chart: '图表', table: '表格', error: '异常', status: '状态', agent_start: '开始', review: '审查', replan_trigger: '重规划' }[type] || type
}

function getNodeColor(kind: VisualNodeKind, active = false): string {
  const palette: Record<VisualNodeKind, string> = { plan: active ? '#54c7ff' : '#2d85c9', thinking: active ? '#7d93ff' : '#5364d4', execution: active ? '#b684ff' : '#7b4fc8', answer: active ? '#ffd36e' : '#c89d35', error: active ? '#ff7d7d' : '#d14e4e' }
  return palette[kind]
}

function formatPlanStatus(status: PlanItemStatus): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '进行中'
    case 'skipped': return '已跳过'
    default: return '待执行'
  }
}

function formatJSON(value: unknown): string {
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function escapeHtml(text: string): string {
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
}

function isMarkdownLike(text: string): boolean {
  return /(^|\n)([-*]\s+|\d+\.\s+|#{1,3}\s+)|```|`[^`]+`/.test(text)
}

function renderRichText(text: string): string {
  const source = escapeHtml((text || '').replace(/\r\n/g, '\n').trim())
  if (!source) return ''
  return source.split(/\n{2,}/).map(renderBlock).join('')
}

function renderBlock(block: string): string {
  const lines = block.split('\n').map(line => line.trimEnd()).filter(Boolean)
  if (!lines.length) return ''
  if (lines.every(line => /^[-*]\s+/.test(line))) return `<ul>${lines.map(line => `<li>${renderInline(line.replace(/^[-*]\s+/, ''))}</li>`).join('')}</ul>`
  if (lines.every(line => /^\d+\.\s+/.test(line))) return `<ol>${lines.map(line => `<li>${renderInline(line.replace(/^\d+\.\s+/, ''))}</li>`).join('')}</ol>`
  if (lines.every(line => /^#{1,3}\s+/.test(line))) return lines.map(line => { const level = Math.min(3, line.match(/^#+/)?.[0].length || 1); return `<h${level}>${renderInline(line.replace(/^#{1,3}\s+/, ''))}</h${level}>` }).join('')
  return `<p>${lines.map(renderInline).join('<br>')}</p>`
}

function renderInline(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>')
}
</script>

<style scoped>
.react-panel{background:radial-gradient(circle at top left,rgba(84,199,255,.12),transparent 35%),linear-gradient(145deg,#131d31,#0f1627);border:1px solid rgba(255,255,255,.08);border-radius:24px;padding:18px}
.react-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:16px}.eyebrow{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#88c9ff;margin-bottom:4px}.react-header h3,.board-head h4{margin:0;color:#f2f6ff;font-size:20px}.header-meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.meta-pill,.follow-btn{border-radius:999px;padding:9px 13px;font-size:12px}.meta-pill{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);color:#cfdcf5}.follow-btn{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#d7e4ff;cursor:pointer}.follow-btn.active{background:rgba(84,199,255,.16);border-color:rgba(84,199,255,.3);color:#f2f8ff}
.react-body{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(340px,.92fr);gap:16px;min-height:560px}.graph-shell,.detail-panel,.result-board{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:20px}.graph-shell{padding:14px}.lane-legend{display:flex;gap:16px;flex-wrap:wrap;color:#b8c7e6;font-size:12px;margin-bottom:10px}.dot{display:inline-block;width:10px;height:10px;border-radius:999px;margin-right:6px}.lane-plan{background:#54c7ff}.lane-think{background:#7d93ff}.lane-act{background:#b684ff}.lane-result{background:#ffd36e}.graph-scroll{overflow-x:auto;overflow-y:hidden}.graph-canvas{height:500px}.detail-panel{padding:16px;overflow-y:auto;max-height:560px}.detail-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.detail-chip{display:inline-flex;padding:4px 10px;border-radius:999px;background:rgba(84,199,255,.16);color:#9fd7ff;font-size:12px;margin-bottom:8px}.detail-top h4{margin:0;color:#f4f7ff;font-size:18px}.detail-meta{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;color:#98a9c9;font-size:12px}.detail-summary,.board-text{color:#e4ebf9;line-height:1.8;font-size:14px}.detail-section{margin-top:14px}.section-title{color:#9fd7ff;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}.detail-section p,.plan-item p{color:#d5deef;font-size:13px;line-height:1.7}.plan-list{display:grid;gap:8px}.plan-item,.raw-event-card{border-radius:14px;padding:10px 12px;background:rgba(255,255,255,.04)}.plan-head,.raw-event-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}.raw-event-head{justify-content:space-between;color:#a9bad8;font-size:12px}.plan-title{flex:1;color:#eff4ff;font-size:13px;font-weight:600}.plan-status{color:#9fb0d3;font-size:12px}.mini-dot{width:8px;height:8px;border-radius:999px;display:inline-block}.dot-completed{background:#67c23a}.dot-in_progress{background:#409eff}.dot-skipped{background:#909399}.dot-pending{background:#7d879c}.detail-table :deep(.el-table__header){background:rgba(7,13,24,.96)}.detail-table :deep(.el-table__body tr){background:rgba(16,25,42,.92)}.chart-preview,.board-chart{border-radius:16px;overflow:hidden;background:rgba(7,13,24,.88);padding:10px}.raw-panel summary{cursor:pointer;color:#c7d5ef}.raw-events{display:grid;gap:10px;margin-top:10px}.raw-block{display:block;margin-top:8px;border-radius:14px;padding:12px 14px;background:rgba(7,13,24,.88);color:#dbe5f8;font-size:12px;line-height:1.7;white-space:pre-wrap;word-break:break-word;overflow-x:auto}.code-block{color:#a7d0ff}.result-board{margin-top:16px;padding:16px}.board-head{margin-bottom:12px}.board-content{display:grid;gap:14px}.board-table{overflow:hidden}.streaming-indicator{display:inline-flex;align-items:center;gap:10px;margin-top:14px;color:#a9bad8;font-size:12px}.streaming-indicator span{width:7px;height:7px;border-radius:50%;background:#54c7ff;animation:bounce 1.2s ease-in-out infinite}.streaming-indicator span:nth-child(2){animation-delay:.16s}.streaming-indicator span:nth-child(3){animation-delay:.32s}
.rich-text :deep(p),.rich-text :deep(ul),.rich-text :deep(ol),.rich-text :deep(h1),.rich-text :deep(h2),.rich-text :deep(h3){margin:0 0 10px}.rich-text :deep(ul),.rich-text :deep(ol){padding-left:20px}.rich-text :deep(li){margin-bottom:6px}.rich-text :deep(strong){color:#f4f8ff;font-weight:700}.rich-text :deep(code){display:inline-block;padding:2px 6px;border-radius:6px;background:rgba(7,13,24,.88);color:#a7d0ff}.rich-text.markdown{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);border-radius:14px;padding:12px 14px}
@keyframes bounce{0%,80%,100%{transform:translateY(0);opacity:.35}40%{transform:translateY(-4px);opacity:1}}@media (max-width:1200px){.react-header{flex-direction:column}.react-body{grid-template-columns:1fr}.header-meta{justify-content:flex-start}.detail-panel{max-height:none}}
</style>
