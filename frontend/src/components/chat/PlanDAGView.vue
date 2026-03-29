<template>
  <div class="plan-dag-view">
    <div v-if="!planGraph" class="dag-placeholder">
      <span class="placeholder-icon">&#x23F3;</span>
      <span>等待 Planner 生成执行计划...</span>
    </div>
    <div v-else class="dag-content">
      <div class="dag-title">{{ planGraph.title }}</div>
      <div v-if="planGraph.summary" class="dag-summary">{{ planGraph.summary }}</div>
      <div v-if="planGraph.change_reason" class="dag-change">&#x1F504; {{ planGraph.change_reason }}</div>
      <div class="dag-nodes">
        <div
          v-for="node in sortedNodes"
          :key="node.id"
          :class="['dag-node', `status-${node.status}`, `kind-${node.kind}`, { active: node.id === activeNodeId }]"
          @click="$emit('selectNode', node.id)"
        >
          <div class="node-status-icon">{{ statusIcon(node.status) }}</div>
          <div class="node-body">
            <div class="node-title">{{ node.title }}</div>
            <div class="node-detail">{{ node.detail }}</div>
            <div v-if="node.tool_hints?.length" class="node-tools">
              <span v-for="t in node.tool_hints" :key="t" class="tool-tag">{{ t }}</span>
            </div>
          </div>
          <div v-if="getDeps(node).length" class="node-deps">
            <span v-for="d in getDeps(node)" :key="d" class="dep-arrow">&#x2190; {{ d }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PlanGraph, PlanGraphNode } from '../../types/agent'

const props = defineProps<{
  planGraph: PlanGraph | null
  activeNodeId?: string
}>()

defineEmits<{
  selectNode: [nodeId: string]
}>()

const sortedNodes = computed(() => {
  if (!props.planGraph) return []
  const nodes = props.planGraph.nodes
  const nodeMap = new Map(nodes.map(n => [n.id, n]))
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

function getDeps(node: PlanGraphNode): string[] {
  if (!node.depends_on?.length || !props.planGraph) return []
  const nodeMap = new Map(props.planGraph.nodes.map(n => [n.id, n]))
  return node.depends_on
    .map(id => nodeMap.get(id)?.title || id)
    .slice(0, 2)
}

function statusIcon(status: string): string {
  const map: Record<string, string> = {
    completed: '\u2705',
    in_progress: '\u{1F504}',
    pending: '\u25CB',
    skipped: '\u23ED',
    blocked: '\u{1F6AB}',
  }
  return map[status] || '\u25CB'
}
</script>

<style scoped>
.plan-dag-view {
  min-height: 200px;
}
.dag-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 200px;
  color: #8b949e;
  font-size: 13px;
}
.placeholder-icon { font-size: 20px; }
.dag-content { }
.dag-title {
  font-size: 15px;
  font-weight: 700;
  color: #58a6ff;
  margin-bottom: 4px;
}
.dag-summary {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 8px;
}
.dag-change {
  font-size: 12px;
  color: #d29922;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: rgba(210,153,34,0.1);
  border-radius: 6px;
}
.dag-nodes {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dag-node {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #21262d;
  background: #161b22;
  cursor: pointer;
  transition: all 0.15s;
}
.dag-node:hover { border-color: #30363d; background: #1c2128; }
.dag-node.active { border-color: #58a6ff; background: rgba(56,139,253,0.08); }
.dag-node.status-completed { border-left: 3px solid #3fb950; }
.dag-node.status-in_progress { border-left: 3px solid #58a6ff; }
.dag-node.status-pending { border-left: 3px solid #484f58; }
.dag-node.status-skipped { border-left: 3px solid #6e7681; opacity: 0.6; }
.dag-node.status-blocked { border-left: 3px solid #f85149; }
.node-status-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.node-body { flex: 1; min-width: 0; }
.node-title {
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  margin-bottom: 2px;
}
.node-detail {
  font-size: 11px;
  color: #8b949e;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.node-tools {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.tool-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(139,148,158,0.15);
  color: #8b949e;
}
.node-deps {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dep-arrow {
  font-size: 10px;
  color: #484f58;
}
</style>
