/** Agent event and chat data types for multi-agent orchestration. */

// ── Agent roles ──
export type AgentRole = 'planner' | 'executor' | 'reviewer' | 'orchestrator'

// ── Event types ──
export type AgentEventType =
  | 'agent_start'
  | 'plan'
  | 'plan_update'
  | 'stage_update'
  | 'thinking'
  | 'action'
  | 'observation'
  | 'review'
  | 'replan_trigger'
  | 'answer'
  | 'chart'
  | 'table'
  | 'error'
  | 'status'

// Legacy compat
export type AgentStepType = AgentEventType

// ── Plan graph structures ──
export type PlanItemStatus = 'pending' | 'in_progress' | 'completed' | 'skipped' | 'blocked'
export type StageGraphStageId =
  | 'intent_recognition'
  | 'semantic_binding'
  | 'tda_mql_draft'
  | 'feasibility_assessment'
  | 'planning'
  | 'metric_execution'
  | 'detail_execution'
  | 'evidence_verification'
  | 'review'
  | 'report_generation'

export type SemanticAnalysisMode = 'analysis' | 'compare' | 'drilldown' | 'hybrid'

export interface SemanticCompareBinding {
  enabled?: boolean
  label?: string
  baseline?: string
  target?: string
  metrics?: string[]
  dimensions?: string[]
  reason?: string
}

export interface SemanticDrilldownBinding {
  enabled?: boolean
  label?: string
  target?: string
  detail_fields?: string[]
  limit?: number
  path?: string[]
  reason?: string
}

export interface SemanticAnalysisModeDetail {
  kind?: SemanticAnalysisMode
  label?: string
  compare?: SemanticCompareBinding
  drilldown?: SemanticDrilldownBinding
  target?: string
  baseline?: string
  detail_fields?: string[]
}

export interface SemanticBindingInfo {
  entry_model?: string
  supporting_models?: string[]
  metrics?: string[]
  dimensions?: string[]
  entity_filters?: Record<string, any[]>
  resolved_filters?: Record<string, any[]>
  filters?: Array<{ field: string; op: string; value?: any }>
  grain?: string
  query_language?: string
  time_context?: {
    grain?: string
    range?: string
  }
  fallback_policy?: string
  compare?: SemanticCompareBinding
  drilldown?: SemanticDrilldownBinding
  analysis_mode?: SemanticAnalysisMode | SemanticAnalysisModeDetail
}

export interface SemanticQueryModeSummary {
  kind: SemanticAnalysisMode
  label: string
  detail: string
  compare?: SemanticCompareBinding | null
  drilldown?: SemanticDrilldownBinding | null
}

export const STAGE_LABELS: Record<string, string> = {
  intent_recognition: '意图识别',
  semantic_binding: '语义绑定',
  tda_mql_draft: 'TDA-MQL 草拟',
  feasibility_assessment: '可行性评估',
  planning: '计划生成',
  metric_execution: '指标执行',
  detail_execution: '明细下钻',
  evidence_verification: '证据校验',
  review: '结果审查',
  report_generation: '报告生成',
  execution: '执行分析',
}

export interface PlanGraphNode {
  id: string
  title: string
  detail: string
  status: PlanItemStatus
  kind: 'goal' | 'schema' | 'query' | 'analysis' | 'knowledge' | 'visualization' | 'answer' | 'task'
  depends_on?: string[]
  tool_hints?: string[]
  done_when?: string
  stage_metadata?: Record<string, any>
  semantic_binding?: SemanticBindingInfo
}

export interface PlanGraphEdge {
  source: string
  target: string
}

export interface PlanGraph {
  title: string
  summary?: string
  nodes: PlanGraphNode[]
  edges?: PlanGraphEdge[]
  active_node_ids?: string[]
  change_reason?: string
  source?: string
}

export interface PlanItem {
  key: string
  title: string
  detail: string
  status: PlanItemStatus
}

// ── Agent Event (WebSocket message) ──
export interface AgentEvent {
  type: AgentEventType
  agent: AgentRole
  step_number: number
  content: string
  timestamp: string
  is_final: boolean
  metadata: {
    // plan
    plan_graph?: PlanGraph
    stage_graph?: PlanGraph
    plan_title?: string
    plan_items?: PlanItem[]
    plan_source?: string
    reasoning?: string
    change_reason?: string
    stage_id?: StageGraphStageId | string
    stage_status?: PlanItemStatus
    stage_reasoning?: string[]
    stage_payload?: Record<string, any>
    stage_llm_call_count?: number
    stage_llm_traces?: Array<{
      llm_call_index?: number
      timestamp?: string
      agent?: string
      operation?: string
      node_id?: string
      node_title?: string
      model?: string
      thinking?: string
      raw_content_preview?: string
      user_prompt_preview?: string
    }>

    // execution
    node_id?: string
    node_title?: string
    plan_node_id?: string
    plan_node_title?: string
    tool_name?: string
    tool_label?: string
    tool_summary?: string
    tool_input?: Record<string, any>
    tool_input_summary?: string
    sql_preview?: string
    sql?: string
    sql_summary?: string

    // observation
    result_summary?: string
    table_data?: { columns: string[]; rows: any[] }
    chart_config?: Record<string, any>
    duration_ms?: number

    // review
    verdict?: 'approve' | 'reject'
    review_points?: string[]
    issues?: string[]
    suggestions?: string[]

    // replan
    reason?: string
    original_node_id?: string

    // answer
    evidence?: string[]

    // semantic context
    semantic_domain?: string
    semantic_subject?: string
    semantic_mode?: string
    semantic_binding?: SemanticBindingInfo
    semantic_context?: {
      dataset_domain?: string
      dataset_domain_label?: string
      request_mode?: string
      request_mode_label?: string
      focus_label?: string
      semantic_subject?: string
    }
  }
}

// Legacy alias
export type AgentStep = AgentEvent

// ── Chat structures ──
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  steps?: AgentEvent[]
  metadata?: Record<string, any>
  timestamp: string
}

export interface Session {
  id: number
  session_id: string
  title: string
  status: string
  created_at: string
  updated_at: string
}

export interface SessionMessageRecord {
  id: number
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  message_type: string
  metadata?: Record<string, any> | null
  created_at: string
}

export interface SemanticModel {
  id: number
  name: string
  label: string
  description: string | null
  source_table: string
  model_type: string
  status: string
  yaml_definition?: string | null
  has_yaml_definition?: boolean
  semantic_kind?: 'entity_dimension' | 'atomic_fact' | 'composite_analysis' | string
  semantic_domain?: string | null
  semantic_grain?: string | null
  entry_enabled?: boolean
  source_count?: number
  join_count?: number
  business_terms?: string[]
  intent_aliases?: string[]
  analysis_patterns?: string[]
  evidence_requirements?: string[]
  fallback_policy?: string
  dimensions?: string[]
  metrics?: string[]
  entities?: Record<string, any>
  time?: Record<string, any>
  supports_entity_resolution?: boolean
}

export interface SemanticQueryResult {
  model_name: string
  model_label: string
  sql: string
  columns: string[]
  rows: Record<string, any>[]
  row_count: number
  warnings: string[]
  resolved_filters?: Record<string, any[]>
  resolution_log?: string[]
  semantic_kind?: string
  semantic_domain?: string
  semantic_grain?: string
}

export interface TableInfo {
  table_name: string
  row_count: number
}

export interface TableSchema {
  table_name: string
  columns: { column_name: string; data_type: string; nullable: string; comment: string }[]
  row_count: number
  preview: Record<string, any>[]
}

export function getStageLabel(stageId: string): string {
  return STAGE_LABELS[stageId] || stageId || '分析中'
}

export function getSemanticQueryMode(binding?: SemanticBindingInfo | null): SemanticQueryModeSummary {
  const analysisMode = binding?.analysis_mode
  const compare = binding?.compare
  const drilldown = binding?.drilldown
  const hasCompare = Boolean(
    compare &&
      (compare.enabled !== false) &&
      (compare.label || compare.baseline || compare.target || compare.metrics?.length || compare.dimensions?.length || compare.reason),
  )
  const hasDrilldown = Boolean(
    drilldown &&
      (drilldown.enabled !== false) &&
      (drilldown.label || drilldown.target || drilldown.detail_fields?.length || typeof drilldown.limit === 'number' || drilldown.path?.length || drilldown.reason),
  )

  let kind: SemanticAnalysisMode = 'analysis'
  let label = '常规分析'

  if (typeof analysisMode === 'string') {
    kind = analysisMode
  } else if (analysisMode?.kind) {
    kind = analysisMode.kind
    label = analysisMode.label || label
  }

  if (hasCompare || kind === 'compare') {
    kind = 'compare'
    label = compare?.label || (typeof analysisMode !== 'string' ? analysisMode?.label : undefined) || '对比查询'
  } else if (hasDrilldown || kind === 'drilldown') {
    kind = 'drilldown'
    label = drilldown?.label || (typeof analysisMode !== 'string' ? analysisMode?.label : undefined) || '下钻查询'
  } else if (kind === 'hybrid') {
    label = (typeof analysisMode !== 'string' ? analysisMode?.label : undefined) || '混合分析'
  } else {
    kind = 'analysis'
    label = (typeof analysisMode !== 'string' ? analysisMode?.label : undefined) || '常规分析'
  }

  const compareDetail = compare
    ? [compare.baseline ? `基线 ${compare.baseline}` : '', compare.target ? `目标 ${compare.target}` : '', compare.metrics?.length ? `指标 ${compare.metrics.slice(0, 2).join(' / ')}` : '', compare.dimensions?.length ? `维度 ${compare.dimensions.slice(0, 2).join(' / ')}` : '']
        .filter(Boolean)
        .join(' · ')
    : ''

  const drilldownDetail = drilldown
    ? [drilldown.target ? `目标 ${drilldown.target}` : '', drilldown.detail_fields?.length ? `字段 ${drilldown.detail_fields.slice(0, 3).join(' / ')}` : '', typeof drilldown.limit === 'number' ? `限额 ${drilldown.limit}` : '']
        .filter(Boolean)
        .join(' · ')
    : ''

  const detail = compareDetail || drilldownDetail || (binding?.metrics?.length ? `指标 ${binding.metrics.slice(0, 2).join(' / ')}` : binding?.dimensions?.length ? `维度 ${binding.dimensions.slice(0, 2).join(' / ')}` : '聚焦常规分析')

  return {
    kind,
    label,
    detail,
    compare: compare || null,
    drilldown: drilldown || null,
  }
}
