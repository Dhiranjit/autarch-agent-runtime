import { useState } from 'react'
import type { Task, TaskStatus } from '../types'

interface TaskListProps {
  tasks: Task[]
}

const STATUS_STYLES: Record<TaskStatus, { bg: string; text: string; border: string }> = {
  PENDING: { bg: 'bg-zinc-800/80', text: 'text-zinc-300', border: 'border-zinc-700' },
  PROCESSING: { bg: 'bg-blue-950/60', text: 'text-blue-300', border: 'border-blue-800' },
  WAITING_APPROVAL: {
    bg: 'bg-amber-950/60',
    text: 'text-amber-300',
    border: 'border-amber-800',
  },
  EXECUTING: { bg: 'bg-indigo-950/60', text: 'text-indigo-300', border: 'border-indigo-800' },
  COMPLETED: {
    bg: 'bg-emerald-950/60',
    text: 'text-emerald-300',
    border: 'border-emerald-800',
  },
  FAILED: { bg: 'bg-rose-950/60', text: 'text-rose-300', border: 'border-rose-800' },
}

export function TaskList({ tasks }: TaskListProps) {
  const [filter, setFilter] = useState<'ALL' | 'WAITING_APPROVAL' | 'COMPLETED'>('ALL')

  const filteredTasks = tasks.filter((t) => {
    if (filter === 'ALL') return true
    return t.status === filter
  })

  if (tasks.length === 0) {
    return (
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 text-xs">
        No tasks recorded yet. Submit an email above to trigger the pipeline.
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800/90 rounded-xl overflow-hidden shadow-xl">
      <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-bold text-zinc-100">Tasks</h3>
          <span className="text-[10px] text-zinc-500 font-mono">
            ({filteredTasks.length}/{tasks.length})
          </span>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1 bg-zinc-950 p-0.5 rounded-lg border border-zinc-800 text-[10px]">
          {(['ALL', 'WAITING_APPROVAL', 'COMPLETED'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setFilter(tab)}
              className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${
                filter === tab
                  ? 'bg-zinc-800 text-zinc-200 font-semibold'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {tab === 'WAITING_APPROVAL' ? 'Waiting' : tab === 'ALL' ? 'All' : 'Done'}
            </button>
          ))}
        </div>
      </div>

      <div className="divide-y divide-zinc-800/60 max-h-[380px] overflow-y-auto">
        {filteredTasks.map((task) => {
          let context: any = {}
          try {
            context = JSON.parse(task.context_json)
          } catch {
            context = {}
          }

          const metadata = context.metadata || {}
          const subject = metadata.subject || 'No subject'
          const summary = metadata.summary
          const style = STATUS_STYLES[task.status] || STATUS_STYLES.PENDING

          return (
            <div
              key={task.id}
              className="p-3 hover:bg-zinc-800/25 transition-colors flex items-start justify-between gap-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-xs text-zinc-100 truncate max-w-[280px]">
                    {subject}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono">
                    ID: {task.id.slice(0, 8)}
                  </span>
                </div>

                {context.source_sender && (
                  <p className="text-[11px] text-zinc-400 mt-0.5 truncate font-mono">
                    From: {context.source_sender}
                  </p>
                )}

                {summary && (
                  <p className="text-[11px] text-zinc-400 mt-1 line-clamp-2 bg-zinc-950/60 p-1.5 rounded border border-zinc-800/50 leading-relaxed">
                    <span className="text-zinc-500 font-medium">Triage:</span> {summary}
                  </p>
                )}

                <span className="text-[10px] text-zinc-500 font-mono block mt-1">
                  {new Date(task.created_at).toLocaleTimeString()}
                </span>
              </div>

              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-medium border ${style.bg} ${style.text} ${style.border} shrink-0 mt-0.5`}
              >
                {task.status}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
