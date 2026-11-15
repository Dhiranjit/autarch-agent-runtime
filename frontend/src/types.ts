export type TaskStatus =
  | 'QUEUED'
  | 'EXECUTING'
  | 'WAITING_APPROVAL'
  | 'COMPLETED'
  | 'FAILED'

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export type UserApprovalAction = 'APPROVE' | 'REJECT'

export interface Task {
  id: string
  source_type: string
  status: TaskStatus
  context_json: string
  messages_json?: string
  result_json: string
  created_at: string
  updated_at: string
}

export interface Approval {
  id: string
  task_id: string
  tool_call_id: string
  tool_name: string
  proposed_args_json: string
  status: ApprovalStatus
  resolved_by: string | null
  created_at: string
  resolved_at: string | null
}

export interface ToolInfo {
  name: string
  description: string
  risk_level?: number
}

export interface ToolResultRecord {
  tool_call_id?: string
  tool_name: string
  args: Record<string, unknown>
  success: boolean
  output: unknown
  status?: string
}

export interface AgentStepRecord {
  step: number
  thought: string
  tool_results: ToolResultRecord[]
}

export interface TaskResultPayload {
  message?: string
  error?: string
  steps?: AgentStepRecord[]
}

export type SSEEventType =
  | 'task_updated'
  | 'agent_step'
  | 'workflow_step'
  | 'subagent_step'
  | 'tool_called'
  | 'tool_result'
  | 'approval_requested'
  | 'approval_resolved'

export interface SSEEnvelope {
  event_type: SSEEventType
  payload: Record<string, unknown>
  timestamp: string
}
