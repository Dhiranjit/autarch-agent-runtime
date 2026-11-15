import type {
  Approval,
  ApprovalStatus,
  SSEEnvelope,
  SSEEventType,
  Task,
  TaskStatus,
  Todo,
  ToolInfo,
  UserApprovalAction,
} from './types'

const API_BASE = '/api'

export async function createTask(
  prompt: string
): Promise<{ task_id: string; status: TaskStatus }> {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to create task: ${res.statusText}`)
  }
  return res.json()
}

export async function getTasks(limit = 30): Promise<Task[]> {
  const res = await fetch(`${API_BASE}/tasks?limit=${limit}`)
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.statusText}`)
  return res.json()
}

export async function getApprovals(
  status?: ApprovalStatus,
  limit = 30
): Promise<Approval[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  const res = await fetch(`${API_BASE}/approvals?${params.toString()}`)
  if (!res.ok) throw new Error(`Failed to fetch approvals: ${res.statusText}`)
  return res.json()
}

export async function resolveApproval(
  approvalId: string,
  action: UserApprovalAction
): Promise<{ approval_id: string; task_id: string; status: ApprovalStatus }> {
  const res = await fetch(`${API_BASE}/approvals/${approvalId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to resolve approval: ${res.statusText}`)
  }
  return res.json()
}

export async function getTools(): Promise<ToolInfo[]> {
  const res = await fetch(`${API_BASE}/tools`)
  if (!res.ok) throw new Error(`Failed to fetch tools: ${res.statusText}`)
  return res.json()
}

export async function getTodos(limit = 50): Promise<Todo[]> {
  const res = await fetch(`${API_BASE}/todos?limit=${limit}`)
  if (!res.ok) throw new Error(`Failed to fetch todos: ${res.statusText}`)
  return res.json()
}

export async function updateTodo(todoId: string, completed: boolean): Promise<Todo> {
  const res = await fetch(`${API_BASE}/todos/${todoId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ completed }),
  })
  if (!res.ok) throw new Error(`Failed to update todo: ${res.statusText}`)
  return res.json()
}

export async function deleteTodo(todoId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/todos/${todoId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Failed to delete todo: ${res.statusText}`)
}

export function subscribeSSE(
  onEvent: (event: SSEEnvelope) => void,
  onStatusChange?: (status: 'connected' | 'connecting' | 'disconnected') => void
): () => void {
  onStatusChange?.('connecting')
  const eventSource = new EventSource(`${API_BASE}/events`)

  eventSource.onopen = () => {
    onStatusChange?.('connected')
  }

  const handleMessage = (rawData: string) => {
    try {
      const parsed: SSEEnvelope = JSON.parse(rawData)
      onEvent(parsed)
    } catch (err) {
      console.error('Failed to parse SSE event data', err)
    }
  }

  eventSource.onmessage = (e) => handleMessage(e.data)

  const namedEvents: SSEEventType[] = [
    'task_updated',
    'agent_step',
    'workflow_step',
    'subagent_step',
    'tool_called',
    'tool_result',
    'approval_requested',
    'approval_resolved',
  ]
  for (const eventType of namedEvents) {
    eventSource.addEventListener(eventType, (e: MessageEvent) => {
      handleMessage(e.data)
    })
  }

  eventSource.onerror = () => {
    onStatusChange?.('disconnected')
  }

  return () => {
    eventSource.close()
    onStatusChange?.('disconnected')
  }
}
