<template>
  <div class="agent-timeline">
    <div class="timeline-header">执行时间轴</div>
    <div class="timeline-list">
      <div
        v-for="(ev, idx) in events"
        :key="idx"
        :class="['tl-item', agentClass(ev), { selected: idx === selectedIndex }]"
        @click="$emit('select', idx)"
      >
        <div class="tl-dot" :class="agentClass(ev)">
          <span class="tl-icon">{{ agentIcon(ev) }}</span>
        </div>
        <div class="tl-body">
          <div class="tl-head">
            <span class="tl-agent-tag" :class="agentClass(ev)">{{ agentLabel(ev) }}</span>
            <span class="tl-type">{{ typeLabel(ev) }}</span>
          </div>
          <div class="tl-content">{{ ev.content?.slice(0, 120) }}</div>
          <div v-if="ev.metadata?.verdict" class="tl-verdict" :class="ev.metadata.verdict">
            {{ ev.metadata.verdict === 'approve' ? 'PASS' : 'REJECT' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentEvent } from '../../types/agent'

defineProps<{
  events: AgentEvent[]
  selectedIndex: number | null
}>()

defineEmits<{
  select: [index: number]
}>()

function agentClass(ev: AgentEvent) {
  return `agent-${ev.agent || 'orchestrator'}`
}

function agentIcon(ev: AgentEvent): string {
  const map: Record<string, string> = {
    planner: '\u{1F9E0}',
    executor: '\u26A1',
    reviewer: '\u{1F50D}',
    orchestrator: '\u{1F3AF}',
  }
  return map[ev.agent] || '\u{1F4AC}'
}

function agentLabel(ev: AgentEvent): string {
  const map: Record<string, string> = {
    planner: 'Planner',
    executor: 'Executor',
    reviewer: 'Reviewer',
    orchestrator: 'System',
  }
  return map[ev.agent] || ev.agent
}

function typeLabel(ev: AgentEvent): string {
  const map: Record<string, string> = {
    agent_start: '',
    plan: 'Plan',
    plan_update: 'Update',
    thinking: 'Think',
    action: 'Action',
    observation: 'Result',
    review: 'Review',
    replan_trigger: 'Replan',
    answer: 'Answer',
    error: 'Error',
    status: '',
  }
  return map[ev.type] || ev.type
}
</script>

<style scoped>
.agent-timeline {
  padding: 12px 0;
}
.timeline-header {
  padding: 0 16px 10px;
  font-size: 13px;
  font-weight: 700;
  color: #8b949e;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tl-item {
  display: flex;
  gap: 10px;
  padding: 8px 16px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: all 0.15s;
}
.tl-item:hover { background: rgba(255,255,255,0.04); }
.tl-item.selected {
  background: rgba(56,139,253,0.1);
  border-left-color: #58a6ff;
}
.tl-dot {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  margin-top: 2px;
}
.tl-dot.agent-planner { background: rgba(56,139,253,0.2); }
.tl-dot.agent-executor { background: rgba(255,166,87,0.2); }
.tl-dot.agent-reviewer { background: rgba(63,185,80,0.2); }
.tl-dot.agent-orchestrator { background: rgba(139,148,158,0.2); }
.tl-icon { font-size: 13px; }
.tl-body { flex: 1; min-width: 0; }
.tl-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.tl-agent-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}
.tl-agent-tag.agent-planner { background: rgba(56,139,253,0.2); color: #58a6ff; }
.tl-agent-tag.agent-executor { background: rgba(255,166,87,0.2); color: #ffa657; }
.tl-agent-tag.agent-reviewer { background: rgba(63,185,80,0.2); color: #3fb950; }
.tl-agent-tag.agent-orchestrator { background: rgba(139,148,158,0.2); color: #8b949e; }
.tl-type {
  font-size: 11px;
  color: #8b949e;
}
.tl-content {
  font-size: 12px;
  color: #c9d1d9;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.tl-verdict {
  display: inline-block;
  margin-top: 4px;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 4px;
}
.tl-verdict.approve { background: rgba(63,185,80,0.2); color: #3fb950; }
.tl-verdict.reject { background: rgba(248,81,73,0.2); color: #f85149; }
</style>
