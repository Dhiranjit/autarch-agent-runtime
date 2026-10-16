import { useState } from 'react'
import { resolveApproval } from '../api'
import type { Approval } from '../types'

interface ApprovalCardProps {
  approval: Approval
  onResolved: () => void
}

export function ApprovalCard({ approval, onResolved }: ApprovalCardProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)

  // Parse arguments
  let parsedArgs: Record<string, any> = {}
  try {
    parsedArgs = JSON.parse(approval.proposed_args_json)
  } catch {
    parsedArgs = {}
  }

  const reasoning = parsedArgs._reasoning
  const [to, setTo] = useState(parsedArgs.to || '')
  const [subject, setSubject] = useState(parsedArgs.subject || '')
  const [body, setBody] = useState(parsedArgs.body || '')

  const handleAction = async (action: 'APPROVE' | 'EDIT' | 'REJECT') => {
    setLoading(true)
    setError(null)
    try {
      const editedArgs =
        action === 'EDIT'
          ? {
              ...parsedArgs,
              to,
              subject,
              body,
            }
          : undefined

      await resolveApproval(approval.id, action, editedArgs)
      onResolved()
    } catch (err: any) {
      setError(err.message || `Failed to ${action.toLowerCase()} proposal`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-zinc-900/90 border border-amber-500/40 rounded-xl p-5 shadow-2xl relative overflow-hidden backdrop-blur-sm">
      <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-amber-500 via-amber-400 to-amber-600" />

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm font-bold text-amber-200">
              {approval.tool_name}
            </span>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/40">
              Level 3 • External Side Effect
            </span>
          </div>
          <p className="text-[11px] text-zinc-400 mt-1 font-mono">
            Approval: <span className="text-zinc-300">{approval.id.slice(0, 8)}</span> • Task:{' '}
            <span className="text-zinc-300">{approval.task_id.slice(0, 8)}</span>
          </p>
        </div>
        <span className="text-[11px] px-2.5 py-1 rounded-md bg-amber-950/80 text-amber-300 font-semibold border border-amber-800/80 shrink-0">
          Awaiting Approval
        </span>
      </div>

      {/* AI Rationale / Reasoning Banner */}
      {reasoning && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-amber-950/25 border border-amber-500/20 text-xs text-amber-200/90 flex items-start gap-2">
          <span className="text-amber-400 text-sm leading-none shrink-0">💡</span>
          <div>
            <span className="font-semibold text-amber-300 block text-[10px] uppercase tracking-wider mb-0.5">
              LLM Triage Reasoning
            </span>
            <span>{reasoning}</span>
          </div>
        </div>
      )}

      {/* Parameters Preview / Edit */}
      {!isEditing ? (
        <div className="bg-zinc-950/90 border border-zinc-800 rounded-lg p-3.5 my-3 space-y-2 text-xs font-mono">
          {parsedArgs.to && (
            <div className="flex items-center gap-2">
              <span className="text-zinc-500 w-16 shrink-0">To:</span>
              <span className="text-zinc-100 font-medium bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                {parsedArgs.to}
              </span>
            </div>
          )}
          {parsedArgs.subject && (
            <div className="flex items-start gap-2">
              <span className="text-zinc-500 w-16 shrink-0">Subject:</span>
              <span className="text-zinc-200 font-medium">{parsedArgs.subject}</span>
            </div>
          )}
          {parsedArgs.body && (
            <div className="pt-2 border-t border-zinc-800/80">
              <span className="text-zinc-500 block text-[11px] mb-1">Proposed Body:</span>
              <p className="text-zinc-300 whitespace-pre-wrap bg-zinc-900/60 p-2.5 rounded border border-zinc-800/60 font-sans text-xs leading-relaxed">
                {parsedArgs.body}
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-zinc-950 border border-amber-500/40 rounded-lg p-3.5 my-3 space-y-3">
          <div className="flex items-center justify-between text-xs text-amber-300 font-semibold">
            <span>Editing Parameters</span>
            <span className="text-[10px] text-zinc-400 font-normal">
              Changes will be logged with actor: user_edited
            </span>
          </div>
          <div>
            <label className="block text-[11px] font-medium text-zinc-400 mb-1">To</label>
            <input
              type="email"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-500 font-mono"
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-zinc-400 mb-1">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-zinc-400 mb-1">Message Body</label>
            <textarea
              rows={3}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-500 font-mono"
            />
          </div>
        </div>
      )}

      {error && (
        <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-900/60 p-2.5 rounded-lg mb-3">
          {error}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-2 border-t border-zinc-800/80 gap-3">
        <button
          type="button"
          onClick={() => setIsEditing(!isEditing)}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 border border-zinc-700 transition-colors cursor-pointer flex items-center gap-1.5"
        >
          {isEditing ? '✕ Cancel Edit' : '✏️ Edit Parameters'}
        </button>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleAction('REJECT')}
            disabled={loading}
            className="px-3.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-rose-950 hover:text-rose-200 hover:border-rose-800 text-xs font-medium text-zinc-300 border border-zinc-700 transition-colors cursor-pointer"
          >
            Reject
          </button>

          {isEditing ? (
            <button
              type="button"
              onClick={() => handleAction('EDIT')}
              disabled={loading}
              className="px-4 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-xs font-semibold text-white transition-colors cursor-pointer shadow-md"
            >
              Confirm & Execute
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleAction('APPROVE')}
              disabled={loading}
              className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white transition-colors cursor-pointer shadow-md flex items-center gap-1.5"
            >
              <span>Approve & Dispatch</span>
              <span>→</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
