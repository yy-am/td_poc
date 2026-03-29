<template>
  <div class="thinking-process">
    <div v-for="(step, idx) in steps" :key="idx" :class="['step-card', `step-${step.type}`]">
      <!-- 思考步骤 -->
      <div v-if="step.type === 'thinking'" class="step-header" @click="toggleStep(idx)">
        <span class="step-icon">&#x1f9e0;</span>
        <span class="step-label">思考 #{{ step.step_number }}</span>
        <span class="step-duration" v-if="step.metadata?.duration_ms">{{ step.metadata.duration_ms }}ms</span>
        <el-icon class="step-toggle"><ArrowDown v-if="expandedSteps[idx]" /><ArrowRight v-else /></el-icon>
      </div>
      <div v-if="step.type === 'thinking' && expandedSteps[idx]" class="step-body thinking-body">
        <p>{{ step.content }}</p>
      </div>

      <!-- 行动步骤 -->
      <div v-if="step.type === 'action'" class="step-header">
        <span class="step-icon">&#x26A1;</span>
        <span class="step-label">执行: {{ step.metadata?.tool_name || '工具调用' }}</span>
      </div>
      <div v-if="step.type === 'action'" class="step-body action-body">
        <pre v-if="step.metadata?.tool_input" class="tool-input">{{ formatJSON(step.metadata.tool_input) }}</pre>
        <div v-if="step.metadata?.tool_input?.query" class="sql-preview">
          <code>{{ step.metadata.tool_input.query }}</code>
        </div>
      </div>

      <!-- 观察步骤 -->
      <div v-if="step.type === 'observation'" class="step-header" @click="toggleStep(idx)">
        <span class="step-icon">&#x1f4ca;</span>
        <span class="step-label">结果</span>
        <span class="step-duration" v-if="step.metadata?.duration_ms">{{ step.metadata.duration_ms }}ms</span>
        <el-icon class="step-toggle"><ArrowDown v-if="expandedSteps[idx]" /><ArrowRight v-else /></el-icon>
      </div>
      <div v-if="step.type === 'observation' && expandedSteps[idx]" class="step-body observation-body">
        <!-- 数据表格 -->
        <div v-if="step.metadata?.table_data" class="data-table-wrapper">
          <el-table
            :data="step.metadata.table_data.rows"
            size="small"
            stripe
            max-height="300"
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
        <!-- SQL -->
        <div v-if="step.metadata?.sql" class="sql-result">
          <code>{{ step.metadata.sql }}</code>
        </div>
        <!-- 文本结果 -->
        <div v-if="!step.metadata?.table_data && !step.metadata?.chart_config" class="text-result">
          <pre>{{ truncate(step.content, 500) }}</pre>
        </div>
      </div>

      <!-- 最终答案 -->
      <div v-if="step.type === 'answer'" class="answer-block">
        <div class="answer-icon">&#x2705;</div>
        <div class="answer-content" v-html="renderMarkdown(step.content)"></div>
      </div>

      <!-- 图表 -->
      <div v-if="step.type === 'answer' && getChartConfig(steps)" class="chart-block">
        <ChartRenderer :option="getChartConfig(steps)!" />
      </div>

      <!-- 错误 -->
      <div v-if="step.type === 'error'" class="error-block">
        <el-alert :title="step.content" type="error" show-icon :closable="false" />
      </div>

      <!-- 状态 -->
      <div v-if="step.type === 'status'" class="status-block">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>{{ step.content }}</span>
      </div>
    </div>

    <!-- 加载动画 -->
    <div v-if="isStreaming && steps.length > 0" class="loading-dots">
      <span></span><span></span><span></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import type { AgentStep } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

const props = defineProps<{
  steps: AgentStep[]
  isStreaming?: boolean
}>()

const expandedSteps = reactive<Record<number, boolean>>({})

// 默认展开所有思考和观察步骤
for (let i = 0; i < 50; i++) {
  expandedSteps[i] = true
}

function toggleStep(idx: number) {
  expandedSteps[idx] = !expandedSteps[idx]
}

function formatJSON(obj: any): string {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '...' : text
}

function renderMarkdown(text: string): string {
  // 简单markdown渲染
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
  max-width: 900px;
}

.step-card {
  margin-bottom: 8px;
  border-radius: 10px;
  overflow: hidden;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}

.step-thinking .step-header { background: #1e3a5f; }
.step-action .step-header { background: #2d1b4e; }
.step-observation .step-header { background: #1b3b2d; }

.step-icon {
  font-size: 16px;
}

.step-label {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  flex: 1;
}

.step-duration {
  font-size: 11px;
  color: #888;
}

.step-toggle {
  color: #888;
  font-size: 12px;
}

.step-body {
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #c0c0c0;
}

.thinking-body {
  background: #162d4a;
}

.action-body {
  background: #231540;
}

.observation-body {
  background: #152e20;
}

.tool-input {
  background: #0f0f23;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #a0d0ff;
  overflow-x: auto;
  margin: 0;
}

.sql-preview, .sql-result {
  background: #0f0f23;
  border-radius: 6px;
  padding: 8px 12px;
  margin-top: 8px;
}

.sql-preview code, .sql-result code {
  color: #67c23a;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.data-table-wrapper {
  margin: 8px 0;
}

.dark-table :deep(.el-table__header) {
  background: #0f0f23;
}

.dark-table :deep(.el-table__body tr) {
  background: #152e20;
}

.text-result pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  color: #a0a0a0;
}

.answer-block {
  background: linear-gradient(135deg, #1a2e1a, #16213e);
  border: 1px solid #2a4a2a;
  border-radius: 12px;
  padding: 18px;
  margin-top: 8px;
}

.answer-icon {
  font-size: 18px;
  margin-bottom: 8px;
}

.answer-content {
  font-size: 14px;
  line-height: 1.8;
  color: #e0e0e0;
}

.answer-content :deep(strong) {
  color: #67c23a;
}

.answer-content :deep(code) {
  background: #0f0f23;
  padding: 2px 6px;
  border-radius: 4px;
  color: #409eff;
  font-size: 13px;
}

.chart-block {
  margin-top: 16px;
  background: #16213e;
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #2a2a4a;
}

.error-block {
  margin-top: 8px;
}

.status-block {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #a0a0a0;
  font-size: 13px;
  padding: 8px 0;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-dots {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409eff;
  animation: bounce 1.2s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
