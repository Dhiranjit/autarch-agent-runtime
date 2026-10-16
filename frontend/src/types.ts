export type TaskStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'WAITING_APPROVAL'
  | 'EXECUTING'
  | 'COMPLETED'
  | 'FAILED'

export type ApprovalStatus =
  | 'pending'
  | 'executing'
  | 'approved'
  | 'rejected'
  | 'failed'

export type ApprovalResolution = 'APPROVE' | 'EDIT' | 'REJECT'

export interface Task {
  id: string
  source_type: string
  status: TaskStatus
  context_json: string
  created_at: string
  updated_at: string
}

export interface Approval {
  id: string
  task_id: string
  tool_name: string
  proposed_args_json: string
  edited_args_json?: string | null
  status: ApprovalStatus
  resolved_by?: string | null
  created_at: string
  resolved_at?: string | null
}

export interface AuditLog {
  id: string
  task_id?: string | null
  approval_id?: string | null
  event_type: string
  tool_name?: string | null
  risk_level?: number | null
  policy_decision?: string | null
  actor: string
  payload_json: string
  created_at: string
}

export interface SSEEnvelope {
  event_type: string
  payload: Record<string, any>
  timestamp: string
}

