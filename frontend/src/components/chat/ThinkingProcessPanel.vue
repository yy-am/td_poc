<template>
  <div class="thinking-process">
    <div v-for="(step, idx) in steps" :key="`${step.timestamp}-${idx}`" class="step-wrapper">
      <div v-if="isPlanStep(step)" class="plan-card">
        <div class="card-title-row">
          <div>
            <div class="eyebrow">{{ step.type === 'plan' ? '执行全景图' : '计划更新' }}</div>
            <h4>{{ step.metadata?.plan_title || (step.type === 'plan' ? '本轮执行计划' : '执行计划已更新') }}</h4>
          </div>
        </div>
        <p class="card-summary">{{ step.content }}</p>
        <p v-if="step.metadata?.change_reason" class="card-reason">
          调整原因：{{ step.metadata.change_reason }}
        </p>

        <div class="plan-list">
          <div
            v-for="item in step.metadata?.plan_items || []"
            :key="item.key"
            class="plan-item"
            :class="`plan-${item.status}`"
          >
            <div class="plan-head">
              <span class="status-dot" :class="`dot-${item.status}`"></span>
              <span class="plan-title">{{ item.title }}</span>
              <span class="plan-status">{{ formatPlanStatus(item.status) }}</span>
            </div>
            <p class="plan-detail">{{ item.detail }}</p>
          </div>
        </div>
      </div>

      <div v-else-if="step.type === 'thinking'" class="step-card step-thinking">
        <div class="step-head">
          <div class="step-title">思考 #{{ step.step_number }}</div>
          <div v-if="step.metadata?.duration_ms" class="step-duration">{{ step.metadata.duration_ms }}ms</div>
        </div>
        <p class="step-text">{{ step.content }}</p>
      </div>

      <div v-else-if="step.type === 'action'" class="step-card step-action">
        <div class="step-head">
          <div class="step-title">{{ step.metadata?.tool_label || '执行工具' }}</div>
        </div>
        <p class="step-text strong">{{ step.metadata?.tool_summary || step.content }}</p>
        <p v-if="step.metadata?.tool_input_summary" class="step-text">{{ step.metadata.tool_input_summary }}</p>
        <div v-if="step.metadata?.sql_summary" class="semantic-chip">{{ step.metadata.sql_summary }}</div>

        <details v-if="step.metadata?.tool_input || step.metadata?.sql_preview" class="raw-details">
          <summary>查看原始参数</summary>
          <pre v-if="step.metadata?.tool_input" class="tool-input">{{ formatJSON(step.metadata.tool_input) }}</pre>
          <code v-if="step.metadata?.sql_preview" class="sql-code">{{ step.metadata.sql_preview }}</code>
        </details>
      </div>

      <div v-else-if="step.type === 'observation'" class="step-card step-observation">
        <div class="step-head">
          <div class="step-title">执行结果</div>
          <div v-if="step.metadata?.duration_ms" class="step-duration">{{ step.metadata.duration_ms }}ms</div>
        </div>
        <p v-if="step.metadata?.result_summary" class="step-text strong">{{ step.metadata.result_summary }}</p>
        <div v-if="step.metadata?.sql_summary" class="semantic-chip">{{ step.metadata.sql_summary }}</div>

        <div v-if="step.metadata?.table_data" class="data-table-wrapper">
          <el-table
            :data="step.metadata.table_data.rows"
            size="small"
            stripe
            max-height="320"
            class="dark-table"
          >
            <el-table-column
              v-for="col in step.metadata.table_data.columns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
              show-overflow-tooltip
            />
          </el-table>
        </div>

        <details v-if="step.metadata?.sql || step.content" class="raw-details">
          <summary>查看原始返回</summary>
          <code v-if="step.metadata?.sql" class="sql-code">{{ step.metadata.sql }}</code>
          <pre v-if="step.content" class="raw-result">{{ truncate(step.content, 1200) }}</pre>
        </details>
      </div>

      <div v-else-if="step.type === 'answer'" class="answer-block">
        <div class="eyebrow">最终回答</div>
        <div class="answer-content" v-html="renderMarkdown(step.content)"></div>
        <div v-if="getChartConfig(steps)" class="chart-block">
          <ChartRenderer :option="getChartConfig(steps)!" />
        </div>
      </div>

      <div v-else-if="step.type === 'error'" class="error-block">
        <el-alert :title="step.content" type="error" show-icon :closable="false" />
      </div>

      <div v-else-if="step.type === 'status'" class="status-block">
        <span class="status-dot status-pulse"></span>
        <span>{{ step.content }}</span>
      </div>
    </div>

    <div v-if="isStreaming && steps.length > 0" class="loading-dots">
      <span></span><span></span><span></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentStep, PlanItemStatus } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

defineProps<{
  steps: AgentStep[]
  isStreaming?: boolean
}>()

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

function formatJSON(obj: any): string {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
}

function getChartConfig(steps: AgentStep[]): Record<string, any> | null {
  for (const step of steps) {
    if (step.metadata?.chart_config) {
      return step.metadata.chart_config
    }
  }
  return null
}
</script>

<style scoped>
.thinking-process {
  max-width: 920px;
}

.step-wrapper {
  margin-bottom: 12px;
}

.plan-card,
.step-card,
.answer-block {
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.plan-card {
  background:
    radial-gradient(circle at top left, rgba(64, 158, 255, 0.18), transparent 40%),
    linear-gradient(145deg, #14253d, #101a2f);
  padding: 18px;
}

.card-title-row,
.step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7fb4ff;
  margin-bottom: 4px;
}

.plan-card h4,
.step-title {
  margin: 0;
  color: #f2f6ff;
  font-size: 16px;
  font-weight: 700;
}

.card-summary,
.card-reason,
.step-text {
  margin: 10px 0 0;
  color: #d7deef;
  line-height: 1.75;
  font-size: 14px;
}

.card-reason {
  color: #9cc4ff;
}

.plan-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.plan-item {
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
}

.plan-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-title {
  flex: 1;
  color: #eef3ff;
  font-size: 14px;
  font-weight: 600;
}

.plan-status {
  font-size: 12px;
  color: #b8c5df;
}

.plan-detail {
  margin: 8px 0 0 18px;
  color: #c9d2e4;
  font-size: 13px;
  line-height: 1.65;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  display: inline-block;
  flex-shrink: 0;
}

.dot-completed {
  background: #67c23a;
}

.dot-in_progress {
  background: #409eff;
  box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.12);
}

.dot-pending,
.dot-skipped {
  background: #909399;
}

.step-card {
  padding: 16px 18px;
}

.step-thinking {
  background: linear-gradient(145deg, #1b2b45, #152237);
}

.step-action {
  background: linear-gradient(145deg, #2b2246, #211736);
}

.step-observation {
  background: linear-gradient(145deg, #1a2f27, #12221b);
}

.step-duration {
  font-size: 12px;
  color: #9eb0d1;
}

.strong {
  color: #f2f6ff;
  font-weight: 600;
}

.semantic-chip {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(64, 158, 255, 0.12);
  color: #b9d7ff;
  font-size: 13px;
  line-height: 1.65;
}

.raw-details {
  margin-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 12px;
}

.raw-details summary {
  cursor: pointer;
  color: #9eb0d1;
  font-size: 13px;
}

.tool-input,
.raw-result,
.sql-code {
  display: block;
  margin-top: 10px;
  border-radius: 12px;
  background: rgba(7, 12, 22, 0.78);
  padding: 12px 14px;
  color: #d7e4ff;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

.data-table-wrapper {
  margin-top: 14px;
}

.dark-table :deep(.el-table__header) {
  background: rgba(8, 17, 32, 0.96);
}

.dark-table :deep(.el-table__body tr) {
  background: rgba(18, 33, 26, 0.95);
}

.answer-block {
  background:
    radial-gradient(circle at top left, rgba(103, 194, 58, 0.14), transparent 42%),
    linear-gradient(145deg, #1a2c21, #152238);
  padding: 20px;
}

.answer-content {
  color: #eef3ff;
  font-size: 14px;
  line-height: 1.85;
}

.answer-content :deep(strong) {
  color: #7ad45c;
}

.answer-content :deep(code) {
  background: rgba(7, 12, 22, 0.72);
  padding: 2px 6px;
  border-radius: 6px;
  color: #9cc4ff;
}

.chart-block {
  margin-top: 18px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(9, 17, 32, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.status-block {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #b8c5df;
  font-size: 13px;
  padding: 8px 2px;
}

.status-pulse {
  background: #409eff;
  animation: pulse 1.4s ease-in-out infinite;
}

.loading-dots {
  display: flex;
  gap: 6px;
  padding: 8px 2px 0;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409eff;
  animation: bounce 1.2s ease-in-out infinite;
}

.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pulse {
  0%, 100% {
    opacity: 0.4;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

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
</style>
