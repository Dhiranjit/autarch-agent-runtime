import { useEffect, useState, useCallback } from 'react'
import { getApprovals, getAuditLogs, getHealth, getTasks, subscribeSSE } from './api'
import type { HealthInfo } from './api'
import { ApprovalCard } from './components/ApprovalCard'
import { AuditTimeline } from './components/AuditTimeline'
import { IngestionPanel } from './components/IngestionPanel'
import { TaskList } from './components/TaskList'
import type { Approval, AuditLog, Task } from './types'

export function App() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [pendingApprovals, setPendingApprovals] = useState<Approval[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [connectionStatus, setConnectionStatus] = useState<
    'connected' | 'connecting' | 'disconnected'
  >('connecting')

  const refreshData = useCallback(async () => {
    try {
      const [t, a, l, h] = await Promise.all([
        getTasks(30),
        getApprovals('pending', 20),
        getAuditLogs(undefined, 50),
        getHealth().catch(() => null),
      ])
      setTasks(t)
      setPendingApprovals(a)
      setAuditLogs(l)
      if (h) setHealth(h)
    } catch (err) {
      console.error('Failed to load initial state', err)
    }
  }, [])

  useEffect(() => {
    let mounted = true
    const init = async () => {
      try {
        const [t, a, l, h] = await Promise.all([
          getTasks(30),
          getApprovals('pending', 20),
          getAuditLogs(undefined, 50),
          getHealth().catch(() => null),
        ])
        if (mounted) {
          setTasks(t)
          setPendingApprovals(a)
          setAuditLogs(l)
          if (h) setHealth(h)
        }
      } catch (err) {
        console.error('Failed to load initial state', err)
      }
    }
    void init()

    const unsubscribe = subscribeSSE(
      () => {
        void refreshData()
      },
      (status) => {
        setConnectionStatus(status)
      }
    )

    return () => {
      mounted = false
      unsubscribe()
    }
  }, [refreshData])

  return (
    <div className="min-h-screen bg-[#090a0f] text-zinc-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 via-indigo-500 to-purple-500 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/20 text-sm">
            S
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-zinc-100 m-0 p-0 leading-tight">
                Sovren
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-mono">
                v0.1.0 • Milestone 1
              </span>
            </div>
            <p className="text-[11px] text-zinc-400">
              Deterministic Personal Assistant Control Loop & Lab
            </p>
          </div>
        </div>

        {/* Right side status indicators */}
        <div className="flex items-center gap-3">
          {/* Active LLM Provider Badge */}
          {health && (
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono border ${
                health.provider === 'openai'
                  ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80'
                  : 'bg-zinc-900 text-zinc-300 border-zinc-800'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  health.provider === 'openai' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
                }`}
              />
              <span>
                {health.provider === 'openai'
                  ? `OpenAI (${health.model})`
                  : 'Mock LLM (Offline)'}
              </span>
            </div>
          )}

          {/* SSE Connection Status */}
          <div className="flex items-center gap-1.5 text-xs font-mono bg-zinc-900 px-2.5 py-1 rounded-full border border-zinc-800">
            <span
              className={`w-2 h-2 rounded-full ${
                connectionStatus === 'connected'
                  ? 'bg-emerald-500 animate-pulse'
                  : connectionStatus === 'connecting'
                  ? 'bg-amber-500 animate-pulse'
                  : 'bg-rose-500'
              }`}
            />
            <span className="text-zinc-300 capitalize text-[11px]">
              {connectionStatus}
            </span>
          </div>

          <button
            type="button"
            onClick={refreshData}
            className="px-3 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-xs text-zinc-300 border border-zinc-700/80 transition-colors cursor-pointer"
          >
            Refresh
          </button>
        </div>
      </header>

      {/* Main Content Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Pending Approvals Section (Level 3 Gate) */}
        <section>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-zinc-100 m-0">
                Action Approval Queue
              </h2>
              {pendingApprovals.length > 0 && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40">
                  {pendingApprovals.length} pending
                </span>
              )}
            </div>
            <span className="text-[11px] text-zinc-400 font-mono">
              Policy Gate • Level 3 External Side Effects
            </span>
          </div>

          {pendingApprovals.length > 0 ? (
            <div
              className={`grid gap-4 ${
                pendingApprovals.length === 1
                  ? 'grid-cols-1 max-w-3xl'
                  : 'grid-cols-1 md:grid-cols-2'
              }`}
            >
              {pendingApprovals.map((approval) => (
                <ApprovalCard
                  key={approval.id}
                  approval={approval}
                  onResolved={refreshData}
                />
              ))}
            </div>
          ) : (
            <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-4 text-center text-xs text-zinc-500 flex items-center justify-center gap-2">
              <span className="text-emerald-500 text-sm">✓</span>
              <span>All external side-effects are clear. No pending human approvals.</span>
            </div>
          )}
        </section>

        {/* Ingestion & State Grids */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Quarantine Ingestion & Active Tasks */}
          <div className="lg:col-span-7 space-y-5">
            <IngestionPanel onIngestSuccess={refreshData} />
            <TaskList tasks={tasks} />
          </div>

          {/* Right Column: Append-Only Audit Trail */}
          <div className="lg:col-span-5">
            <AuditTimeline logs={auditLogs} />
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
