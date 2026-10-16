import { useState } from 'react'
import type { AuditLog } from '../types'

interface AuditTimelineProps {
  logs: AuditLog[]
}

const ACTOR_STYLES: Record<string, string> = {
  policy_auto: 'bg-purple-950/70 text-purple-300 border-purple-800/80',
  user_approved: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/80',
  user_edited: 'bg-cyan-950/70 text-cyan-300 border-cyan-800/80',
  user_rejected: 'bg-rose-950/70 text-rose-300 border-rose-800/80',
  system: 'bg-zinc-800 text-zinc-300 border-zinc-700',
}

export function AuditTimeline({ logs }: AuditTimelineProps) {
  const [filter, setFilter] = useState<'ALL' | 'TOOLS' | 'APPROVALS'>('ALL')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const filteredLogs = logs.filter((log) => {
    if (filter === 'ALL') return true
    if (filter === 'TOOLS') {
      return log.event_type.startsWith('tool_') || Boolean(log.tool_name)
    }
    if (filter === 'APPROVALS') {
      return log.event_type.startsWith('approval_')
    }
    return true
  })

  const handleCopyPayload = (id: string, payload: any) => {
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  if (logs.length === 0) {
    return (
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 text-xs">
        No audit entries recorded yet.
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800/90 rounded-xl overflow-hidden shadow-xl flex flex-col">
      {/* Header */}
      <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-bold text-zinc-100">Audit Trail</h3>
          <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
            Append-Only
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">
            ({filteredLogs.length}/{logs.length})
          </span>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1 bg-zinc-950 p-0.5 rounded-lg border border-zinc-800 text-[10px]">
          {(['ALL', 'TOOLS', 'APPROVALS'] as const).map((tab) => (
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
              {tab === 'ALL' ? 'All' : tab === 'TOOLS' ? 'Tools' : 'Approvals'}
            </button>
          ))}
        </div>
      </div>

      {/* Log Feed */}
      <div className="divide-y divide-zinc-800/60 max-h-[580px] overflow-y-auto">
        {filteredLogs.map((log) => {
          let parsedPayload: any = {}
          try {
            parsedPayload = JSON.parse(log.payload_json)
          } catch {
            parsedPayload = log.payload_json
          }

          const actorStyle = ACTOR_STYLES[log.actor] || ACTOR_STYLES.system
          const isExpanded = expandedId === log.id

          return (
            <div key={log.id} className="p-3 hover:bg-zinc-800/25 transition-colors">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 font-mono flex-wrap">
                  <span className="font-semibold text-zinc-200 text-[11px]">{log.event_type}</span>
                  {log.tool_name && (
                    <span className="text-zinc-400 text-[11px]">
                      • tool: <strong className="text-zinc-300">{log.tool_name}</strong>
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-zinc-500 font-mono shrink-0">
                  {new Date(log.created_at).toLocaleTimeString()}
                </span>
              </div>

              <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono border ${actorStyle}`}>
                  {log.actor}
                </span>

                {log.policy_decision && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded font-mono bg-zinc-950 text-zinc-300 border border-zinc-800">
                    {log.policy_decision}
                  </span>
                )}

                {log.risk_level !== null && log.risk_level !== undefined && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded font-mono bg-zinc-950 text-amber-400/90 border border-amber-900/40">
                    L{log.risk_level}
                  </span>
                )}

                <button
                  type="button"
                  onClick={() => setExpandedId(isExpanded ? null : log.id)}
                  className="text-[10px] text-indigo-400 hover:text-indigo-300 ml-auto cursor-pointer font-medium"
                >
                  {isExpanded ? 'Hide Payload' : 'View Payload'}
                </button>
              </div>

              {isExpanded && (
                <div className="mt-2 p-2 bg-zinc-950 border border-zinc-800 rounded-lg text-[10px] font-mono text-zinc-300 relative group">
                  <div className="flex items-center justify-between border-b border-zinc-800/80 pb-1 mb-1.5 text-zinc-500">
                    <span>Payload Data</span>
                    <button
                      type="button"
                      onClick={() => handleCopyPayload(log.id, parsedPayload)}
                      className="text-indigo-400 hover:text-indigo-300 cursor-pointer"
                    >
                      {copiedId === log.id ? '✓ Copied' : 'Copy'}
                    </button>
                  </div>
                  <pre className="whitespace-pre-wrap overflow-x-auto max-h-48 leading-relaxed">
                    {JSON.stringify(parsedPayload, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
