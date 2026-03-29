<template>
  <div class="react-panel">
    <div class="react-header">
      <div>
        <div class="eyebrow">ReAct 过程图</div>
        <h3>计划、思考、行动、观察、回答</h3>
      </div>
      <button
        class="follow-btn"
        :class="{ active: followLatest }"
        type="button"
        @click="enableFollowLatest"
      >
        {{ followLatest ? '跟随最新中' : '切回最新步骤' }}
      </button>
    </div>

    <div class="react-body">
      <div class="graph-shell">
        <div class="lane-legend">
          <span><i class="dot lane-plan"></i>规划</span>
          <span><i class="dot lane-think"></i>思考</span>
          <span><i class="dot lane-act"></i>执行</span>
          <span><i class="dot lane-result"></i>结果</span>
        </div>
        <div class="graph-scroll">
          <div ref="chartRef" class="graph-canvas" :style="{ width: `${chartWidth}px` }"></div>
        </div>
      </div>

      <div v-if="selectedStep" class="detail-panel">
        <div class="detail-top">
          <div>
            <div class="detail-chip">{{ getStepCategory(selectedStep.type) }}</div>
            <h4>{{ getStepTitle(selectedStep) }}</h4>
          </div>
          <div class="detail-meta">
            <span v-if="selectedStep.metadata?.duration_ms">{{ selectedStep.metadata.duration_ms }}ms</span>
            <span>步骤 #{{ selectedStep.step_number }}</span>
          </div>
        </div>

        <p class="detail-summary">{{ selectedStep.content }}</p>

        <template v-if="isPlanStep(selectedStep)">
          <div class="detail-section">
            <div class="section-title">计划明细</div>
            <div class="plan-list">
              <div
                v-for="item in selectedStep.metadata?.plan_items || []"
                :key="item.key"
                class="plan-item"
                :class="`status-${item.status}`"
              >
                <div class="plan-head">
                  <span class="mini-dot" :class="`dot-${item.status}`"></span>
                  <span class="plan-title">{{ item.title }}</span>
                  <span class="plan-status">{{ formatPlanStatus(item.status) }}</span>
                </div>
                <p>{{ item.detail }}</p>
              </div>
            </div>
          </div>
          <div v-if="selectedStep.metadata?.change_reason" class="detail-section">
            <div class="section-title">这次为什么更新计划</div>
            <p>{{ selectedStep.metadata.change_reason }}</p>
          </div>
        </template>

        <template v-else>
          <div v-if="selectedStep.metadata?.tool_label || selectedStep.metadata?.tool_summary" class="detail-section">
            <div class="section-title">工具说明</div>
            <p v-if="selectedStep.metadata?.tool_label"><strong>{{ selectedStep.metadata.tool_label }}</strong></p>
            <p v-if="selectedStep.metadata?.tool_summary">{{ selectedStep.metadata.tool_summary }}</p>
            <p v-if="selectedStep.metadata?.tool_input_summary">{{ selectedStep.metadata.tool_input_summary }}</p>
          </div>

          <div v-if="selectedStep.metadata?.sql_summary" class="detail-section">
            <div class="section-title">SQL 在做什么</div>
            <p>{{ selectedStep.metadata.sql_summary }}</p>
          </div>

          <div v-if="selectedStep.metadata?.result_summary" class="detail-section">
            <div class="section-title">结果解读</div>
            <p>{{ selectedStep.metadata.result_summary }}</p>
          </div>

          <div v-if="selectedStep.metadata?.table_data" class="detail-section">
            <div class="section-title">结果预览</div>
            <el-table
              :data="selectedStep.metadata.table_data.rows"
              size="small"
              stripe
              max-height="220"
              class="detail-table"
            >
              <el-table-column
                v-for="col in selectedStep.metadata.table_data.columns"
                :key="col"
                :prop="col"
                :label="col"
                min-width="120"
                show-overflow-tooltip
              />
            </el-table>
          </div>

          <div v-if="selectedChartConfig" class="detail-section">
            <div class="section-title">图表预览</div>
            <div class="chart-preview">
              <ChartRenderer :option="selectedChartConfig" />
            </div>
          </div>

          <details v-if="hasRawDetails(selectedStep)" class="detail-section raw-panel">
            <summary>查看原始内容</summary>
            <pre v-if="selectedStep.metadata?.tool_input" class="raw-block">{{ formatJSON(selectedStep.metadata.tool_input) }}</pre>
            <code v-if="selectedStep.metadata?.sql_preview" class="raw-block code-block">{{ selectedStep.metadata.sql_preview }}</code>
            <code v-if="selectedStep.metadata?.sql" class="raw-block code-block">{{ selectedStep.metadata.sql }}</code>
            <pre v-if="selectedStep.content" class="raw-block">{{ truncate(selectedStep.content, 2400) }}</pre>
          </details>
        </template>
      </div>
    </div>

    <div v-if="isStreaming" class="streaming-indicator">
      <span></span><span></span><span></span>
      <em>正在更新当前步骤图</em>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { AgentStep, AgentStepType, PlanItemStatus } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

const props = defineProps<{
  steps: AgentStep[]
  isStreaming?: boolean
}>()

const chartRef = ref<HTMLElement>()
const selectedIndex = ref(-1)
const followLatest = ref(true)
const chartWidth = ref(900)

let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const selectedStep = computed(() => {
  if (!props.steps.length) return null
  const idx = selectedIndex.value >= 0 ? selectedIndex.value : props.steps.length - 1
  return props.steps[Math.min(idx, props.steps.length - 1)] || null
})

const selectedChartConfig = computed<Record<string, any> | null>(() => {
  if (!selectedStep.value) return null
  if (selectedStep.value.metadata?.chart_config) {
    return selectedStep.value.metadata.chart_config
  }
  if (selectedStep.value.type === 'answer') {
    for (let idx = props.steps.length - 1; idx >= 0; idx -= 1) {
      if (props.steps[idx].metadata?.chart_config) {
        return props.steps[idx].metadata.chart_config!
      }
    }
  }
  return null
})

onMounted(() => {
  nextTick(() => {
    initChart()
    syncSelection()
    renderChart()
  })
})

watch(
  () => props.steps,
  async () => {
    if (!props.steps.length) return
    syncSelection()
    await nextTick()
    renderChart()
  },
  { deep: true }
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

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

  resizeObserver = new ResizeObserver(() => {
    renderChart()
  })
  resizeObserver.observe(chartRef.value.parentElement as Element)
}

function syncSelection() {
  if (!props.steps.length) {
    selectedIndex.value = -1
    return
  }

  if (followLatest.value || selectedIndex.value >= props.steps.length) {
    selectedIndex.value = props.steps.length - 1
  }
}

function enableFollowLatest() {
  followLatest.value = true
  selectedIndex.value = props.steps.length - 1
  renderChart()
}

function renderChart() {
  if (!chart || !chartRef.value) return

  const shellWidth = chartRef.value.parentElement?.clientWidth || 900
  chartWidth.value = Math.max(shellWidth, props.steps.length * 160 + 180)
  nextTick(() => {
    if (!chart || !chartRef.value) return

    const laneY: Record<string, number> = {
      plan: 80,
      plan_update: 80,
      thinking: 190,
      status: 190,
      action: 300,
      observation: 300,
      answer: 410,
      error: 410,
      chart: 410,
      table: 410,
    }

    const nodes = props.steps.map((step, index) => {
      const x = 100 + index * 150
      const y = laneY[step.type] ?? 410
      const isActive = index === selectedIndex.value
      return {
        name: `${index + 1}`,
        value: step.step_number,
        x,
        y,
        symbolSize: isActive ? 64 : 52,
        itemStyle: {
          color: getStepColor(step.type, isActive),
          borderColor: isActive ? '#f7fbff' : 'rgba(255,255,255,0.28)',
          borderWidth: isActive ? 3 : 1,
          shadowBlur: isActive ? 22 : 10,
          shadowColor: getStepColor(step.type, true),
        },
        label: {
          show: true,
          formatter: () => `${index + 1}\n${shortLabel(step)}`,
          color: '#f4f7ff',
          fontSize: 11,
          lineHeight: 14,
          fontWeight: 600,
        },
      }
    })

    const edges = props.steps.slice(1).map((_, index) => ({
      source: index,
      target: index + 1,
      lineStyle: {
        color: 'rgba(143, 170, 220, 0.45)',
        width: 2,
        curveness: 0.12,
      },
      symbol: ['none', 'arrow'],
      symbolSize: 10,
    }))

    chart.setOption(
      {
        animationDurationUpdate: 260,
        grid: { left: 0, right: 0, top: 0, bottom: 0 },
        xAxis: { show: false, min: 0, max: chartWidth.value },
        yAxis: { show: false, min: 0, max: 500 },
        graphic: [
          laneText('规划', 26, 80),
          laneText('思考', 26, 190),
          laneText('执行', 26, 300),
          laneText('结果', 26, 410),
          laneDivider(0, 135),
          laneDivider(0, 245),
          laneDivider(0, 355),
        ],
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(10, 18, 33, 0.95)',
          borderColor: 'rgba(255,255,255,0.08)',
          textStyle: { color: '#eef3ff' },
          formatter: (params: any) => {
            if (params.dataType !== 'node') return ''
            const step = props.steps[params.dataIndex]
            return `
              <div style="min-width:200px">
                <div style="font-weight:700;margin-bottom:6px">${getStepTitle(step)}</div>
                <div style="color:#9fb7e7;font-size:12px">${getStepCategory(step.type)}</div>
                <div style="margin-top:8px;line-height:1.6">${escapeHtml(truncate(step.content, 120))}</div>
              </div>
            `
          },
        },
        series: [
          {
            type: 'graph',
            layout: 'none',
            coordinateSystem: null,
            roam: false,
            data: nodes,
            edges,
            edgeSymbol: ['none', 'arrow'],
            edgeSymbolSize: 10,
            lineStyle: {
              opacity: 1,
            },
            emphasis: {
              scale: false,
            },
          },
        ],
      },
      true
    )

    chart.resize({ width: chartWidth.value, height: 500 })
  })
}

function laneText(label: string, x: number, y: number) {
  return {
    type: 'text',
    left: x,
    top: y - 12,
    style: {
      text: label,
      fill: 'rgba(188, 203, 231, 0.72)',
      font: '12px sans-serif',
    },
    silent: true,
  }
}

function laneDivider(x: number, y: number) {
  return {
    type: 'line',
    left: x,
    top: y,
    shape: { x1: 0, y1: 0, x2: chartWidth.value, y2: 0 },
    style: {
      stroke: 'rgba(255,255,255,0.08)',
      lineWidth: 1,
    },
    silent: true,
  }
}

function shortLabel(step: AgentStep): string {
  if (step.type === 'plan' || step.type === 'plan_update') return '计划'
  if (step.metadata?.tool_label) return step.metadata.tool_label
  return getStepCategory(step.type)
}

function getStepCategory(type: AgentStepType): string {
  const map: Record<AgentStepType, string> = {
    plan: '执行计划',
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
  }
  return map[type]
}

function getStepTitle(step: AgentStep): string {
  if (step.type === 'plan' || step.type === 'plan_update') {
    return step.metadata?.plan_title || getStepCategory(step.type)
  }
  if (step.type === 'action') {
    return step.metadata?.tool_label || '执行工具'
  }
  if (step.type === 'observation') {
    return '执行结果'
  }
  return getStepCategory(step.type)
}

function getStepColor(type: AgentStepType, active = false): string {
  const palette: Record<AgentStepType, string> = {
    plan: active ? '#54c7ff' : '#2d85c9',
    plan_update: active ? '#64d6ff' : '#2f94c2',
    thinking: active ? '#7d93ff' : '#5364d4',
    status: active ? '#8ea2c7' : '#5f6c8f',
    action: active ? '#b684ff' : '#7b4fc8',
    observation: active ? '#66d19f' : '#2f9c6a',
    answer: active ? '#ffd36e' : '#c89d35',
    chart: active ? '#ffd36e' : '#c89d35',
    table: active ? '#ffd36e' : '#c89d35',
    error: active ? '#ff7d7d' : '#d14e4e',
    agent_start: active ? '#8ea2c7' : '#5f6c8f',
    review: active ? '#66d19f' : '#2f9c6a',
    replan_trigger: active ? '#ffd36e' : '#c89d35',
  }
  return palette[type]
}

function isPlanStep(step: AgentStep): boolean {
  return step.type === 'plan' || step.type === 'plan_update'
}

function formatPlanStatus(status: PlanItemStatus): string {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'in_progress':
      return '进行中'
    case 'skipped':
      return '已跳过'
    default:
      return '待执行'
  }
}

function hasRawDetails(step: AgentStep): boolean {
  return Boolean(step.metadata?.tool_input || step.metadata?.sql_preview || step.metadata?.sql || step.content)
}

function formatJSON(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
}
</script>

<style scoped>
.react-panel {
  background:
    radial-gradient(circle at top left, rgba(84, 199, 255, 0.12), transparent 35%),
    linear-gradient(145deg, #131d31, #0f1627);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  padding: 18px;
}

.react-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #88c9ff;
  margin-bottom: 4px;
}

.react-header h3 {
  margin: 0;
  color: #f2f6ff;
  font-size: 20px;
}

.follow-btn {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #d7e4ff;
  border-radius: 999px;
  padding: 10px 14px;
  cursor: pointer;
  transition: 0.2s ease;
}

.follow-btn.active {
  background: rgba(84, 199, 255, 0.16);
  border-color: rgba(84, 199, 255, 0.3);
  color: #f2f8ff;
}

.react-body {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.9fr);
  gap: 16px;
  min-height: 560px;
}

.graph-shell,
.detail-panel {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 20px;
}

.graph-shell {
  padding: 14px;
  display: flex;
  flex-direction: column;
}

.lane-legend {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  color: #b8c7e6;
  font-size: 12px;
  margin-bottom: 10px;
}

.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  margin-right: 6px;
}

.lane-plan { background: #54c7ff; }
.lane-think { background: #7d93ff; }
.lane-act { background: #b684ff; }
.lane-result { background: #66d19f; }

.graph-scroll {
  overflow-x: auto;
  overflow-y: hidden;
}

.graph-canvas {
  height: 500px;
}

.detail-panel {
  padding: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.detail-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.detail-chip {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(84, 199, 255, 0.16);
  color: #9fd7ff;
  font-size: 12px;
  margin-bottom: 8px;
}

.detail-top h4 {
  margin: 0;
  color: #f4f7ff;
  font-size: 18px;
}

.detail-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  color: #98a9c9;
  font-size: 12px;
}

.detail-summary {
  color: #e4ebf9;
  line-height: 1.75;
  font-size: 14px;
  margin: 0 0 12px;
}

.detail-section {
  margin-top: 14px;
}

.section-title {
  color: #9fd7ff;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.detail-section p,
.plan-item p {
  color: #d5deef;
  font-size: 13px;
  line-height: 1.7;
}

.plan-list {
  display: grid;
  gap: 8px;
}

.plan-item {
  border-radius: 14px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.04);
}

.plan-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.plan-title {
  flex: 1;
  color: #eff4ff;
  font-size: 13px;
  font-weight: 600;
}

.plan-status {
  color: #9fb0d3;
  font-size: 12px;
}

.mini-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}

.dot-completed { background: #67c23a; }
.dot-in_progress { background: #409eff; }
.dot-skipped { background: #909399; }
.dot-pending { background: #7d879c; }

.detail-table :deep(.el-table__header) {
  background: rgba(7, 13, 24, 0.96);
}

.detail-table :deep(.el-table__body tr) {
  background: rgba(16, 25, 42, 0.92);
}

.chart-preview {
  border-radius: 16px;
  overflow: hidden;
  background: rgba(7, 13, 24, 0.88);
  padding: 10px;
}

.raw-panel summary {
  cursor: pointer;
  color: #c7d5ef;
}

.raw-block {
  display: block;
  margin-top: 10px;
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(7, 13, 24, 0.88);
  color: #dbe5f8;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

.code-block {
  color: #a7d0ff;
}

.streaming-indicator {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  color: #a9bad8;
  font-size: 12px;
}

.streaming-indicator span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #54c7ff;
  animation: bounce 1.2s ease-in-out infinite;
}

.streaming-indicator span:nth-child(2) { animation-delay: 0.16s; }
.streaming-indicator span:nth-child(3) { animation-delay: 0.32s; }

@keyframes bounce {
  0%, 80%, 100% {
    transform: translateY(0);
    opacity: 0.35;
  }
  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

@media (max-width: 1200px) {
  .react-body {
    grid-template-columns: 1fr;
  }

  .detail-panel {
    min-height: 420px;
  }
}
</style>
