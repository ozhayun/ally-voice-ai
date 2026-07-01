import { useState, useEffect } from 'react'
import { Phone, PhoneOff, Loader2, Smartphone, BarChart2 } from 'lucide-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { cn, formatPhone, toE164, formatCost } from '@/lib/utils'
import { useAgentStore } from '@/store/agentStore'
import { useCallStore } from '@/store/callStore'
import { useCallStatus } from '@/hooks/useCallStatus'
import { api } from '@/services/api'

const SENTIMENT_COLOR: Record<string, string> = {
  Positive: 'text-emerald-400',
  Neutral: 'text-yellow-400',
  Negative: 'text-red-400',
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = (seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

export function CallPanel() {
  const [phone, setPhone] = useState('')
  const [leadName, setLeadName] = useState('')
  const [leadEmail, setLeadEmail] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [callerInfo, setCallerInfo] = useState<{ number: string; index: number; size: number } | null>(null)
  const vapiAssistantId = useAgentStore((s) => s.vapiAssistantId)
  const callStatus = useCallStore((s) => s.callStatus)
  const callId = useCallStore((s) => s.callId)
  const setCallId = useCallStore((s) => s.setCallId)
  const setCallStatus = useCallStore((s) => s.setCallStatus)
  const reset = useCallStore((s) => s.reset)
  const [ending, setEnding] = useState(false)

  async function handleEnd() {
    if (callId) {
      setEnding(true)
      try {
        await api.endCall(callId)
      } catch {
        // best-effort
      } finally {
        setEnding(false)
      }
    }
    reset()
  }

  function handleReset() {
    // Sync the log before clearing callId so hanging-up-from-phone calls aren't lost
    if (callId) {
      void api.syncCallLog(callId).catch(() => null)
    }
    reset()
  }

  useCallStatus(callId)

  useEffect(() => {
    if (callStatus !== 'in-progress') { setElapsed(0); return }
    const interval = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(interval)
  }, [callStatus])

  const { data: logs = [] } = useQuery({
    queryKey: ['call-logs'],
    queryFn: api.getCallLogs,
    refetchInterval: 15000,
  })
  const latestLog = callId ? logs.find((l) => l.vapi_call_id === callId) : undefined

  const triggerMutation = useMutation({
    mutationFn: () => api.triggerCall(toE164(phone), vapiAssistantId!, leadName.trim() || undefined, leadEmail.trim() || undefined),
    onMutate: () => setCallStatus('connecting'),
    onSuccess: (data) => {
      setCallId(data.call_id)
      setCallStatus('in-progress')
      if (data.caller_number) setCallerInfo({ number: data.caller_number, index: data.pool_index, size: data.pool_size })
      toast.success('Call started!')
    },
    onError: () => {
      setCallStatus('error')
      toast.error('Failed to start call. Check Vapi credentials.')
    },
  })

  const canCall =
    !!vapiAssistantId &&
    leadName.trim().length > 0 &&
    leadEmail.trim().includes('@') &&
    (phone.startsWith('+') ? phone.replace(/\D/g, '').length >= 7 : phone.replace(/\D/g, '').length >= 10)

  const isActive = callStatus === 'in-progress' || callStatus === 'connecting'
  const isIdle = callStatus === 'idle' || callStatus === 'ended' || callStatus === 'failed' || callStatus === 'error'

  return (
    <div className="border-t border-zinc-800 flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
        <Smartphone size={14} className="text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-100">Live Test Environment</h3>
      </div>

      {/* Lead info + phone */}
      <div className="px-4 pt-4 pb-3 flex flex-col gap-2">
        <div className="flex gap-2">
          <div className={cn(
            'flex-1 flex items-center bg-zinc-950 border rounded-lg overflow-hidden transition-colors',
            isActive ? 'border-zinc-700 opacity-60' : 'border-zinc-700 focus-within:border-indigo-500',
          )}>
            <input
              type="text"
              placeholder="Lead name"
              value={leadName}
              onChange={(e) => setLeadName(e.target.value)}
              disabled={isActive}
              className="flex-1 bg-transparent px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none"
            />
          </div>
          <div className={cn(
            'flex-1 flex items-center bg-zinc-950 border rounded-lg overflow-hidden transition-colors',
            isActive ? 'border-zinc-700 opacity-60' : 'border-zinc-700 focus-within:border-indigo-500',
          )}>
            <input
              type="email"
              placeholder="lead@company.com"
              value={leadEmail}
              onChange={(e) => setLeadEmail(e.target.value)}
              disabled={isActive}
              className="flex-1 bg-transparent px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none"
            />
          </div>
        </div>

        <div className="flex gap-2">
          <div className={cn(
            'flex-1 flex items-center bg-zinc-950 border rounded-lg overflow-hidden transition-colors',
            isActive ? 'border-zinc-700 opacity-60' : 'border-zinc-700 focus-within:border-indigo-500',
          )}>
            <input
              type="tel"
              autoComplete="tel"
              placeholder="+972-50-000-0000 or (555) 000-0000"
              value={phone}
              onChange={(e) => setPhone(formatPhone(e.target.value))}
              disabled={isActive}
              className="flex-1 bg-transparent px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none"
            />
          </div>

          {isIdle ? (
            <button
              onClick={() => triggerMutation.mutate()}
              disabled={!canCall || triggerMutation.isPending}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all whitespace-nowrap',
                canCall && !triggerMutation.isPending
                  ? 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-600/20'
                  : 'bg-zinc-800 text-zinc-500 cursor-not-allowed',
              )}
            >
              {triggerMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <span className="h-2 w-2 rounded-full border-2 border-current" />
              )}
              Start Call
            </button>
          ) : (
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
            >
              <PhoneOff size={14} />
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Active call status bar */}
      {isActive && (
        <div className="mx-4 mb-3 flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] font-bold text-emerald-400 tracking-widest uppercase">
              {callStatus === 'connecting' ? 'Connecting' : 'In Progress'}
            </span>
            {callerInfo?.number && (
              <span className="text-[11px] text-zinc-500">
                · from {callerInfo.number}
                {callerInfo.size > 0 && <span className="text-zinc-700"> {callerInfo.index}/{callerInfo.size}</span>}
              </span>
            )}
          </div>
          <div className="flex items-center gap-5">
            {callStatus === 'in-progress' && (
              <div>
                <p className="text-[9px] text-zinc-600 uppercase tracking-wider">Duration</p>
                <p className="text-sm font-mono text-zinc-200">{formatElapsed(elapsed)}</p>
              </div>
            )}
            <BarChart2 size={18} className="text-zinc-600" />
            <button
              onClick={handleEnd}
              disabled={ending}
              className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-60"
            >
              {ending ? <Loader2 size={11} className="animate-spin" /> : <Phone size={11} />}
              End
            </button>
          </div>
        </div>
      )}

      {!vapiAssistantId && (
        <p className="px-4 pb-3 text-xs text-zinc-700">Configure your agent first to enable calls.</p>
      )}

      {/* Metrics */}
      <div className="grid grid-cols-3 border-t border-zinc-800 divide-x divide-zinc-800">
        <MetricCell
          label="Avg Latency"
          value={latestLog?.latency_ms != null ? `${latestLog.latency_ms}ms` : '-'}
        />
        <MetricCell
          label="Token Cost"
          value={latestLog ? formatCost(latestLog.cost_usd) : '-'}
        />
        <MetricCell
          label="Sentiment"
          value={latestLog?.sentiment ?? '-'}
          valueClass={latestLog ? SENTIMENT_COLOR[latestLog.sentiment] : undefined}
        />
      </div>
    </div>
  )
}

interface MetricCellProps {
  label: string
  value: string
  valueClass?: string
}

function MetricCell({ label, value, valueClass }: MetricCellProps) {
  return (
    <div className="px-4 py-3">
      <p className="text-[9px] font-bold tracking-widest uppercase text-zinc-600 mb-1">{label}</p>
      <p className={cn('text-sm font-semibold text-zinc-200', valueClass)}>{value}</p>
    </div>
  )
}
