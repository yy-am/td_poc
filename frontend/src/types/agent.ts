/** Agent event and chat data types for multi-agent orchestration. */

// ── Agent roles ──
export type AgentRole = 'planner' | 'executor' | 'reviewer' | 'orchestrator'

// ── Event types ──
export type AgentEventType =
  | 'agent_start'
  | 'plan'
  | 'plan_update'
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

export interface PlanGraphNode {
  id: string
  title: string
  detail: string
  status: PlanItemStatus
  kind: 'goal' | 'schema' | 'query' | 'analysis' | 'knowledge' | 'visualization' | 'answer' | 'task'
  depends_on?: string[]
  tool_hints?: string[]
  done_when?: string
  semantic_binding?: {
    models?: string[]
    metrics?: string[]
    dimensions?: string[]
    filters?: Array<{ field: string; op: string; value?: any }>
    grain?: string
    fallback_to_sql?: boolean
  }
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
    plan_title?: string
    plan_items?: PlanItem[]
    plan_source?: string
    reasoning?: string
    change_reason?: string

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
  description: string
  source_table: string
  model_type: 'physical' | 'semantic' | 'metric'
  status: string
}

export interface SemanticQueryResult {
  model_name: string
  model_label: string
  sql: string
  columns: string[]
  rows: Record<string, any>[]
  row_count: number
  warnings: string[]
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
