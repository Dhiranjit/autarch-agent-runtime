import { useCallback, useEffect, useId, useRef, useState } from 'react'
import {
  createTask,
  getApprovals,
  getTasks,
  getTools,
  resolveApproval,
  subscribeSSE,
} from './api'
import type {
  Approval,
  SSEEnvelope,
  Task,
  TaskResultPayload,
  TaskStatus,
  ToolInfo,
  UserApprovalAction,
} from './types'

function parseJson<T>(raw: string | undefined, fallback: T): T {
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function extractTaskPrompt(task: Task): string {
  const ctx = parseJson<Record<string, unknown>>(task.context_json, {})
  if (typeof ctx.prompt === 'string' && ctx.prompt.trim()) {
    return ctx.prompt
  }
  return task.context_json || '(empty task)'
}

function StatusBadge({ status }: { status: TaskStatus }) {
  const styles: Record<TaskStatus, string> = {
    QUEUED: 'bg-zinc-800 text-zinc-300 border-zinc-700',
    EXECUTING: 'bg-indigo-950/70 text-indigo-300 border-indigo-700/70',
    WAITING_APPROVAL: 'bg-amber-950/70 text-amber-300 border-amber-700/70',
    COMPLETED: 'bg-emerald-950/70 text-emerald-300 border-emerald-700/70',
    FAILED: 'bg-rose-950/70 text-rose-300 border-rose-700/70',
  }
  const icons: Record<TaskStatus, string> = {
    QUEUED: '○',
    EXECUTING: '◌',
    WAITING_APPROVAL: '!',
    COMPLETED: '✓',
    FAILED: '✕',
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono border ${styles[status] ?? styles.QUEUED}`}
    >
      <span aria-hidden="true">{icons[status] ?? '○'}</span>
      <span>{status}</span>
    </span>
  )
}

export function App() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [eventsByTask, setEventsByTask] = useState<Record<string, SSEEnvelope[]>>({})
  const [prompt, setPrompt] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<
    'connected' | 'connecting' | 'disconnected'
  >('connecting')

  const promptInputRef = useRef<HTMLTextAreaElement>(null)
  const promptId = useId()
  const helpId = useId()
  const errorId = useId()

  const refreshState = useCallback(async () => {
    try {
      const [taskList, pendingApprovals] = await Promise.all([
        getTasks(30),
        getApprovals('PENDING', 30).catch(() => [] as Approval[]),
      ])
      setTasks(taskList)
      setApprovals(pendingApprovals)
      setSelectedTaskId((current) => current ?? taskList[0]?.id ?? null)
    } catch (err) {
      console.error('Failed to refresh state', err)
    }
  }, [])

  useEffect(() => {
    let mounted = true
    const init = async () => {
      try {
        const [taskList, pendingApprovals, toolList] = await Promise.all([
          getTasks(30),
          getApprovals('PENDING', 30).catch(() => [] as Approval[]),
          getTools().catch(() => [] as ToolInfo[]),
        ])
        if (!mounted) return
        setTasks(taskList)
        setApprovals(pendingApprovals)
        setSelectedTaskId((current) => current ?? taskList[0]?.id ?? null)
        setTools(toolList)
      } catch (err) {
        console.error('Failed to load initial state', err)
      }
    }
    void init()

    const unsubscribe = subscribeSSE(
      (event) => {
        const taskId = typeof event.payload.task_id === 'string' ? event.payload.task_id : null
        if (taskId) {
          setEventsByTask((prev) => ({
            ...prev,
            [taskId]: [...(prev[taskId] ?? []), event],
          }))
        }
        if (
          event.event_type === 'task_updated' ||
          event.event_type === 'approval_requested' ||
          event.event_type === 'approval_resolved'
        ) {
          void refreshState()
        }
      },
      (status) => setConnectionStatus(status)
    )

    return () => {
      mounted = false
      unsubscribe()
    }
  }, [refreshState])

  const submitTask = async () => {
    const trimmed = prompt.trim()
    if (!trimmed) {
      setFormError('Please enter a task for the agent to run.')
      promptInputRef.current?.focus()
      return
    }

    setIsSubmitting(true)
    setFormError(null)
    try {
      const res = await createTask(trimmed)
      setPrompt('')
      setSelectedTaskId(res.task_id)
      await refreshState()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to start task.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleResolveApproval = async (
    approvalId: string,
    action: UserApprovalAction
  ) => {
    setResolvingId(approvalId)
    try {
      await resolveApproval(approvalId, action)
      await refreshState()
    } catch (err) {
      console.error('Failed to resolve approval', err)
    } finally {
      setResolvingId(null)
    }
  }

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    void submitTask()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      void submitTask()
    }
  }

  const selectedTask = tasks.find((t) => t.id === selectedTaskId) ?? tasks[0] ?? null
  const liveEvents = selectedTask ? eventsByTask[selectedTask.id] ?? [] : []
  const persistedResult = selectedTask
    ? parseJson<TaskResultPayload>(selectedTask.result_json, {})
    : {}
  const taskApprovals = selectedTask
    ? approvals.filter((a) => a.task_id === selectedTask.id && a.status === 'PENDING')
    : []

  return (
    <div className="min-h-screen bg-[#090a0f] text-zinc-100 flex flex-col font-sans">
      <header className="border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            aria-hidden="true"
            className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-sm"
          >
            S
          </div>
          <div>
            <h1 className="text-base font-bold text-zinc-100 leading-tight m-0">
              Sovren Agent Orchestrator
            </h1>
            <p className="text-xs text-zinc-400 m-0">
              Native tool loop, quarantine state workflows &amp; policy-gated approvals
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono bg-zinc-900 px-3 py-1 rounded-full border border-zinc-800">
          <span
            aria-hidden="true"
            className={`w-2 h-2 rounded-full ${
              connectionStatus === 'connected'
                ? 'bg-emerald-500'
                : connectionStatus === 'connecting'
                ? 'bg-amber-400'
                : 'bg-rose-500'
            }`}
          />
          <span className="text-zinc-300 capitalize">SSE: {connectionStatus}</span>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto p-6 space-y-6">
        <section className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-5">
          <form onSubmit={handleSubmit} noValidate className="space-y-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor={promptId} className="text-sm font-medium text-zinc-200">
                Task Prompt
              </label>
              <span id={helpId} className="text-xs text-zinc-400">
                {tools.length > 0
                  ? `Available tools & workflows: ${tools.map((t) => t.name).join(', ')}. Press Ctrl/Cmd+Enter or click Run Task.`
                  : 'Describe what you want the orchestrator to do. Press Ctrl/Cmd+Enter or click Run Task.'}
              </span>
              <textarea
                ref={promptInputRef}
                id={promptId}
                name="prompt"
                rows={3}
                required
                value={prompt}
                onChange={(e) => {
                  setPrompt(e.target.value)
                  if (formError) setFormError(null)
                }}
                onKeyDown={handleKeyDown}
                aria-invalid={formError ? 'true' : undefined}
                aria-describedby={formError ? `${helpId} ${errorId}` : helpId}
                placeholder="e.g. Give me my daily briefing from unread emails, create a task for any urgent items, and send a confirmation email to sarah.chen@company.com"
                className="w-full rounded-lg bg-zinc-950 border border-zinc-700 px-3.5 py-2.5 text-base text-zinc-100 placeholder:text-zinc-500 focus-visible:outline-2 focus-visible:outline-indigo-500 focus-visible:outline-offset-2"
              />
            </div>

            {formError && (
              <p id={errorId} role="alert" className="text-sm text-rose-400 m-0">
                {formError}
              </p>
            )}

            <div className="flex items-center justify-between gap-4">
              {tools.length > 0 ? (
                <ul
                  role="list"
                  className="flex flex-wrap gap-2 list-none p-0 m-0"
                  aria-label="Registered tools"
                >
                  {tools.map((tool) => (
                    <li
                      key={tool.name}
                      className="text-xs font-mono px-2.5 py-1 rounded-md bg-zinc-950 border border-zinc-800 text-zinc-300"
                    >
                      {tool.name}
                      {typeof tool.risk_level === 'number' ? ` (L${tool.risk_level})` : ''}
                    </li>
                  ))}
                </ul>
              ) : (
                <span />
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 text-sm font-medium text-white transition-colors cursor-pointer min-h-10 shrink-0 focus-visible:outline-2 focus-visible:outline-indigo-400 focus-visible:outline-offset-2"
              >
                {isSubmitting ? 'Starting…' : 'Run Task'}
              </button>
            </div>
          </form>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <section className="lg:col-span-8 bg-zinc-900/60 border border-zinc-800 rounded-xl p-5 space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-zinc-800 pb-3">
              <div className="space-y-1 min-w-0">
                <h2 className="text-sm font-semibold text-zinc-100 m-0">
                  Live Execution Steps
                </h2>
                {selectedTask ? (
                  <p className="text-sm text-zinc-300 m-0 break-words">
                    {extractTaskPrompt(selectedTask)}
                  </p>
                ) : (
                  <p className="text-sm text-zinc-500 m-0">
                    Submit a task above to watch the orchestrator loop in real time.
                  </p>
                )}
              </div>
              {selectedTask && <StatusBadge status={selectedTask.status} />}
            </div>

            {taskApprovals.length > 0 && (
              <div
                role="region"
                aria-label="Pending tool approvals"
                className="rounded-xl bg-amber-950/30 border border-amber-700/70 p-4 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-amber-300 m-0">
                    Action Required: Pending Human Approval ({taskApprovals.length})
                  </h3>
                </div>
                <ul role="list" className="space-y-2.5 list-none p-0 m-0">
                  {taskApprovals.map((approval) => {
                    const args = parseJson<Record<string, unknown>>(
                      approval.proposed_args_json,
                      {}
                    )
                    const isBusy = resolvingId === approval.id
                    return (
                      <li
                        key={approval.id}
                        className="rounded-lg bg-zinc-950/90 border border-amber-800/60 p-3 space-y-2 text-xs"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-semibold text-amber-200">
                            Tool: {approval.tool_name}
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              disabled={isBusy}
                              aria-label={`Approve ${approval.tool_name}`}
                              onClick={() =>
                                void handleResolveApproval(approval.id, 'APPROVE')
                              }
                              className="px-3 py-1.5 min-h-8 rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-60 text-white font-medium cursor-pointer focus-visible:outline-2 focus-visible:outline-emerald-400 focus-visible:outline-offset-2"
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              disabled={isBusy}
                              aria-label={`Reject ${approval.tool_name}`}
                              onClick={() =>
                                void handleResolveApproval(approval.id, 'REJECT')
                              }
                              className="px-3 py-1.5 min-h-8 rounded-md bg-rose-700 hover:bg-rose-600 disabled:opacity-60 text-white font-medium cursor-pointer focus-visible:outline-2 focus-visible:outline-rose-400 focus-visible:outline-offset-2"
                            >
                              Reject
                            </button>
                          </div>
                        </div>
                        <pre className="m-0 p-2 rounded bg-zinc-900 text-zinc-300 overflow-x-auto font-mono">
                          {JSON.stringify(args, null, 2)}
                        </pre>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}

            {selectedTask && (
              <div className="space-y-4">
                {liveEvents.length > 0 ? (
                  <ol role="list" className="space-y-2.5 list-none p-0 m-0">
                    {liveEvents.map((ev, idx) => (
                      <li
                        key={`${ev.timestamp}-${idx}`}
                        className="rounded-lg bg-zinc-950/90 border border-zinc-800/90 p-3 text-xs space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-zinc-400 font-mono">
                          <span className="text-indigo-300 font-semibold">
                            {ev.event_type}
                            {typeof ev.payload.step === 'number' ? ` • Step ${ev.payload.step}` : ''}
                          </span>
                          <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                        </div>

                        {ev.event_type === 'agent_step' && (
                          <div className="text-zinc-200">
                            {ev.payload.phase === 'thinking' ? (
                              <span className="text-zinc-400">Calling LLM…</span>
                            ) : (
                              <div className="space-y-1">
                                <p className="m-0">
                                  {String(ev.payload.message || '(no message)')}
                                </p>
                                <p className="m-0 text-zinc-400 font-mono">
                                  Proposed tool calls: {String(ev.payload.tool_count ?? 0)}
                                </p>
                              </div>
                            )}
                          </div>
                        )}

                        {ev.event_type === 'workflow_step' && (
                          <div className="text-cyan-300 font-mono">
                            Workflow [{String(ev.payload.workflow)}] node{' '}
                            <span className="font-semibold">{String(ev.payload.node)}</span> →{' '}
                            {String(ev.payload.status)}
                          </div>
                        )}

                        {ev.event_type === 'subagent_step' && (
                          <div className="text-purple-300 font-mono">
                            Subagent [{String(ev.payload.subagent)}] step{' '}
                            {String(ev.payload.step)} ({String(ev.payload.phase)})
                          </div>
                        )}

                        {ev.event_type === 'tool_called' && (
                          <div className="space-y-1">
                            <div className="font-mono text-amber-300">
                              ▶ {String(ev.payload.tool_name)}
                            </div>
                            <pre className="m-0 p-2 rounded bg-zinc-900 text-zinc-300 overflow-x-auto font-mono">
                              {JSON.stringify(ev.payload.args, null, 2)}
                            </pre>
                          </div>
                        )}

                        {ev.event_type === 'tool_result' && (
                          <div className="space-y-1">
                            <div
                              className={`font-mono ${
                                ev.payload.success ? 'text-emerald-400' : 'text-rose-400'
                              }`}
                            >
                              {ev.payload.success ? '✓' : '✕'} {String(ev.payload.tool_name)} result
                            </div>
                            <pre className="m-0 p-2 rounded bg-zinc-900 text-zinc-300 overflow-x-auto font-mono">
                              {JSON.stringify(ev.payload.output, null, 2)}
                            </pre>
                          </div>
                        )}

                        {ev.event_type === 'approval_requested' && (
                          <div className="text-amber-300 font-mono">
                            ⏸ Approval requested for tool{' '}
                            <span className="font-semibold">
                              {String(ev.payload.tool_name)}
                            </span>
                          </div>
                        )}

                        {ev.event_type === 'approval_resolved' && (
                          <div className="text-indigo-300 font-mono">
                            ▶ Approval resolved: {String(ev.payload.status)}
                          </div>
                        )}

                        {ev.event_type === 'task_updated' && (
                          <div className="text-zinc-300 font-mono">
                            Task status → {String(ev.payload.status)}
                          </div>
                        )}
                      </li>
                    ))}
                  </ol>
                ) : persistedResult.steps && persistedResult.steps.length > 0 ? (
                  <ol role="list" className="space-y-2.5 list-none p-0 m-0">
                    {persistedResult.steps.map((step) => (
                      <li
                        key={step.step}
                        className="rounded-lg bg-zinc-950/90 border border-zinc-800/90 p-3 text-xs space-y-2"
                      >
                        <div className="font-mono text-indigo-300 font-semibold">
                          Step {step.step}
                        </div>
                        {step.thought && <p className="m-0 text-zinc-200">{step.thought}</p>}
                        {step.tool_results.map((tr, i) => (
                          <div key={i} className="rounded bg-zinc-900 p-2 space-y-1 font-mono">
                            <div className={tr.success ? 'text-emerald-400' : 'text-rose-400'}>
                              {tr.success ? '✓' : '✕'} {tr.tool_name}
                            </div>
                            <div className="text-zinc-400">
                              args: {JSON.stringify(tr.args)}
                            </div>
                            <div className="text-zinc-200">
                              output: {JSON.stringify(tr.output)}
                            </div>
                          </div>
                        ))}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-xs text-zinc-500 m-0">
                    {selectedTask.status === 'EXECUTING' || selectedTask.status === 'QUEUED'
                      ? 'Waiting for agent steps…'
                      : 'No tool steps recorded for this task.'}
                  </p>
                )}

                {persistedResult.message && (
                  <div className="rounded-lg bg-emerald-950/30 border border-emerald-800/60 p-3.5 text-sm text-emerald-100">
                    <div className="text-xs font-mono text-emerald-400 mb-1">Final Answer</div>
                    <p className="m-0 whitespace-pre-wrap">{persistedResult.message}</p>
                  </div>
                )}

                {persistedResult.error && (
                  <div
                    role="alert"
                    className="rounded-lg bg-rose-950/40 border border-rose-800/60 p-3.5 text-sm text-rose-200"
                  >
                    <div className="text-xs font-mono text-rose-400 mb-1">Error</div>
                    <p className="m-0 whitespace-pre-wrap">{persistedResult.error}</p>
                  </div>
                )}
              </div>
            )}
          </section>

          <aside className="lg:col-span-4 bg-zinc-900/60 border border-zinc-800 rounded-xl p-5 space-y-3">
            <h2 className="text-sm font-semibold text-zinc-100 m-0">Recent Tasks</h2>
            {tasks.length === 0 ? (
              <p className="text-xs text-zinc-500 m-0">No tasks yet.</p>
            ) : (
              <ul role="list" className="space-y-2 list-none p-0 m-0">
                {tasks.map((task) => {
                  const isSelected = selectedTask?.id === task.id
                  return (
                    <li key={task.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedTaskId(task.id)}
                        className={`w-full text-left rounded-lg p-3 border transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-indigo-400 focus-visible:outline-offset-2 ${
                          isSelected
                            ? 'bg-zinc-800/90 border-indigo-500/70'
                            : 'bg-zinc-950/70 border-zinc-800 hover:border-zinc-700'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <StatusBadge status={task.status} />
                          <span className="text-[11px] font-mono text-zinc-500">
                            {new Date(task.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        <p className="text-xs text-zinc-200 m-0 line-clamp-2">
                          {extractTaskPrompt(task)}
                        </p>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </aside>
        </div>
      </main>
    </div>
  )
}

export default App
