<template>
  <div class="agent-detail-panel">
    <div class="detail-header">
      <span class="detail-agent-tag" :class="`agent-${event.agent}`">{{ agentLabel }}</span>
      <span class="detail-type">{{ typeLabel }}</span>
      <span v-if="event.metadata?.duration_ms" class="detail-duration">{{ event.metadata.duration_ms }}ms</span>
    </div>

    <div class="detail-content">{{ event.content }}</div>

    <div v-if="event.metadata?.reasoning" class="detail-section">
      <div class="section-title">Planner 推理过程</div>
      <div class="section-body reasoning">{{ event.metadata.reasoning }}</div>
    </div>

    <div v-if="event.metadata?.tool_name" class="detail-section">
      <div class="section-title">工具调用</div>
      <div class="tool-info">
        <span class="tool-name">{{ event.metadata.tool_label || event.metadata.tool_name }}</span>
        <span v-if="event.metadata.tool_summary" class="tool-summary">{{ event.metadata.tool_summary }}</span>
      </div>
      <div v-if="event.metadata.sql_preview || event.metadata.sql" class="sql-block">
        <pre>{{ event.metadata.sql_preview || event.metadata.sql }}</pre>
      </div>
    </div>

    <div v-if="event.metadata?.verdict" class="detail-section">
      <div class="section-title">审查结论</div>
      <div :class="['verdict-badge', event.metadata.verdict]">
        {{ event.metadata.verdict === 'approve' ? 'PASS' : 'REJECT' }}
      </div>
      <ul v-if="event.metadata.review_points?.length" class="review-list">
        <li v-for="(point, index) in event.metadata.review_points" :key="index">{{ point }}</li>
      </ul>
      <div v-if="event.metadata.issues?.length" class="issues">
        <div class="issue-title">发现的问题</div>
        <ul>
          <li v-for="(issue, index) in event.metadata.issues" :key="index" class="issue-item">{{ issue }}</li>
        </ul>
      </div>
      <div v-if="event.metadata.suggestions?.length" class="suggestions">
        <div class="suggest-title">改进建议</div>
        <ul>
          <li v-for="(suggestion, index) in event.metadata.suggestions" :key="index">{{ suggestion }}</li>
        </ul>
      </div>
    </div>

    <div v-if="event.metadata?.table_data" class="detail-section">
      <div class="section-title">查询结果 ({{ event.metadata.result_summary || '' }})</div>
      <el-table
        :data="tableRows"
        size="small"
        stripe
        max-height="200"
        class="result-table"
      >
        <el-table-column
          v-for="col in event.metadata.table_data.columns"
          :key="col"
          :prop="col"
          :label="col"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
    </div>

    <div v-if="event.metadata?.chart_config" class="detail-section">
      <div class="section-title">图表</div>
      <ChartRenderer :option="event.metadata.chart_config" />
    </div>

    <div v-if="event.metadata?.evidence?.length" class="detail-section">
      <div class="section-title">数据证据</div>
      <ul class="evidence-list">
        <li v-for="(evidence, index) in event.metadata.evidence" :key="index">{{ evidence }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentEvent } from '../../types/agent'
import ChartRenderer from '../charts/ChartRenderer.vue'

const props = defineProps<{
  event: AgentEvent
}>()

const agentLabel = computed(() => {
  const map: Record<string, string> = {
    planner: 'Planner',
    executor: 'Executor',
    reviewer: 'Reviewer',
    orchestrator: 'System',
  }
  return map[props.event.agent] || props.event.agent
})

const typeLabel = computed(() => {
  const map: Record<string, string> = {
    agent_start: '开始',
    plan: '计划',
    plan_update: '计划更新',
    thinking: '思考',
    action: '执行',
    observation: '执行结果',
    review: '审查',
    replan_trigger: '重规划',
    answer: '最终报告',
    error: '错误',
    status: '状态',
  }
  return map[props.event.type] || props.event.type
})

const tableRows = computed(() => {
  const tableData = props.event.metadata?.table_data
  if (!tableData?.columns || !tableData?.rows) return []
  return tableData.rows.map((row: any) => {
    if (Array.isArray(row)) {
      const mapped: Record<string, any> = {}
      tableData.columns.forEach((col: string, index: number) => {
        mapped[col] = row[index]
      })
      return mapped
    }
    return row
  })
})
</script>

<style scoped>
.agent-detail-panel {
  padding: 14px 20px;
  background: #0d1117;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.detail-agent-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.detail-agent-tag.agent-planner {
  background: rgba(56, 139, 253, 0.2);
  color: #58a6ff;
}

.detail-agent-tag.agent-executor {
  background: rgba(255, 166, 87, 0.2);
  color: #ffa657;
}

.detail-agent-tag.agent-reviewer {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.detail-agent-tag.agent-orchestrator {
  background: rgba(139, 148, 158, 0.2);
  color: #8b949e;
}

.detail-type {
  font-size: 12px;
  color: #8b949e;
}

.detail-duration {
  font-size: 11px;
  color: #6e7681;
  margin-left: auto;
}

.detail-content {
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.6;
  margin-bottom: 10px;
}

.detail-section {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #21262d;
}

.section-title {
  font-size: 12px;
  font-weight: 700;
  color: #8b949e;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.section-body {
  font-size: 12px;
  color: #c9d1d9;
  line-height: 1.6;
}

.reasoning {
  font-style: italic;
  color: #a5b4c7;
}

.tool-info {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.tool-name {
  font-weight: 600;
  color: #ffa657;
  font-size: 12px;
}

.tool-summary {
  font-size: 11px;
  color: #8b949e;
}

.sql-block {
  background: #161b22;
  border-radius: 6px;
  padding: 8px 12px;
  overflow-x: auto;
  margin-top: 6px;
}

.sql-block pre {
  font-size: 11px;
  color: #7ee787;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-family: 'Consolas', 'Monaco', monospace;
}

.verdict-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 4px;
  margin-bottom: 6px;
}

.verdict-badge.approve {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.verdict-badge.reject {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.review-list,
.evidence-list {
  padding-left: 16px;
  font-size: 12px;
  color: #c9d1d9;
}

.review-list li,
.evidence-list li {
  margin: 2px 0;
}

.issues {
  margin-top: 6px;
}

.issue-title,
.suggest-title {
  font-size: 11px;
  font-weight: 600;
  color: #f85149;
  margin-bottom: 4px;
}

.suggest-title {
  color: #d29922;
}

.issue-item {
  color: #f85149;
}

.suggestions {
  margin-top: 6px;
}

.suggestions li {
  font-size: 12px;
  color: #d29922;
}

.result-table {
  margin-top: 6px;
}

:deep(.el-table) {
  --el-table-bg-color: #0d1117;
  --el-table-tr-bg-color: #0d1117;
  --el-table-header-bg-color: #161b22;
  --el-table-border-color: #21262d;
  --el-table-text-color: #c9d1d9;
  --el-table-header-text-color: #8b949e;
  font-size: 11px;
}
</style>
