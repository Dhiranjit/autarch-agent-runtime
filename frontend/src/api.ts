import type {
  Approval,
  ApprovalResolution,
  ApprovalStatus,
  AuditLog,
  SSEEnvelope,
  Task,
} from './types'

const API_BASE = '/api'

export interface HealthInfo {
  status: string
  app: string
  provider: 'openai' | 'mock'
  model: string
}

export async function getHealth(): Promise<HealthInfo> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

export async function getTasks(limit = 50): Promise<Task[]> {
  const res = await fetch(`${API_BASE}/tasks?limit=${limit}`)
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.statusText}`)
  return res.json()
}

export async function getApprovals(status?: ApprovalStatus, limit = 50): Promise<Approval[]> {
  const url = new URL(`${window.location.origin}${API_BASE}/approvals`)
  url.searchParams.set('limit', String(limit))
  if (status) {
    url.searchParams.set('status', status)
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to fetch approvals: ${res.statusText}`)
  return res.json()
}

export async function getAuditLogs(taskId?: string, limit = 100): Promise<AuditLog[]> {
  const url = new URL(`${window.location.origin}${API_BASE}/audit`)
  url.searchParams.set('limit', String(limit))
  if (taskId) {
    url.searchParams.set('task_id', taskId)
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to fetch audit logs: ${res.statusText}`)
  return res.json()
}

export async function ingestEmail(payload: {
  sender: string
  recipient?: string
  subject: string
  body: string
  thread_id?: string
}): Promise<{ task_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/tasks/ingest-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to ingest email: ${res.statusText}`)
  }
  return res.json()
}

export async function resolveApproval(
  approvalId: string,
  action: ApprovalResolution,
  editedArgs?: Record<string, any>
): Promise<{ approval_id: string; status: ApprovalStatus; task_id: string }> {
  const res = await fetch(`${API_BASE}/approvals/${approvalId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action,
      edited_args: editedArgs,
      resolved_by: 'user',
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to resolve approval: ${res.statusText}`)
  }
  return res.json()
}

export function subscribeSSE(
  onMessage: (event: SSEEnvelope) => void,
  onStatusChange?: (status: 'connected' | 'connecting' | 'disconnected') => void
): () => void {
  onStatusChange?.('connecting')
  const eventSource = new EventSource(`${API_BASE}/events`)

  eventSource.onopen = () => {
    onStatusChange?.('connected')
  }

  eventSource.onmessage = (e) => {
    try {
      const data: SSEEnvelope = JSON.parse(e.data)
      onMessage(data)
    } catch (err) {
      console.error('Failed to parse SSE event data', err)
    }
  }

  // Also listen for specific event types if backend publishes named events
  const namedEvents = [
    'task_updated',
    'approval_requested',
    'approval_resolved',
    'audit_logged',
  ]
  namedEvents.forEach((eventType) => {
    eventSource.addEventListener(eventType, (e: any) => {
      try {
        const data: SSEEnvelope = JSON.parse(e.data)
        onMessage(data)
      } catch (err) {
        console.error(`Failed to parse SSE event for ${eventType}`, err)
      }
    })
  })

  eventSource.onerror = () => {
    onStatusChange?.('disconnected')
  }

  return () => {
    eventSource.close()
    onStatusChange?.('disconnected')
  }
}

