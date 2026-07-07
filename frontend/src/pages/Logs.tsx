import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, List, Search, CheckCircle2, ChevronLeft, ChevronRight, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/services/api'
import { formatDuration, formatCost, cn } from '@/lib/utils'
import type { CallLog } from '@/types'

const PAGE_SIZE = 10

const SENTIMENT_DOT: Record<string, string> = {
  Positive: 'bg-emerald-400',
  Neutral: 'bg-yellow-400',
  Negative: 'bg-red-400',
}

interface TranscriptLine {
  role: 'AI' | 'USER'
  text: string
}

function parseTranscript(raw: string): TranscriptLine[] {
  const lines: TranscriptLine[] = []
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    if (/^AI:\s*/i.test(trimmed)) {
      lines.push({ role: 'AI', text: trimmed.replace(/^AI:\s*/i, '') })
    } else if (/^User:\s*/i.test(trimmed)) {
      lines.push({ role: 'USER', text: trimmed.replace(/^User:\s*/i, '') })
    } else if (lines.length > 0) {
      // continuation of previous line
      lines[lines.length - 1].text += ' ' + trimmed
    }
  }
  return lines
}

interface DrawerProps {
  log: CallLog
  index: number
  onClose: () => void
}

function TranscriptDrawer({ log, index, onClose }: DrawerProps) {
  const lines = parseTranscript(log.transcript)
  const isMeetingBooked = log.is_booked

  return (
    <div className="w-[420px] flex-shrink-0 bg-[#111] border-l border-zinc-800 flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-4 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-zinc-100">
              Call &mdash; {new Date(log.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </h3>
            <p className="text-xs text-zinc-500 mt-0.5">
              {formatDuration(log.duration_seconds)} Duration &bull; ID: {index + 1}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 divide-x divide-zinc-800 border-b border-zinc-800 flex-shrink-0">
        <div className="px-4 py-3 text-center">
          <p className="text-[9px] font-bold tracking-widest uppercase text-zinc-600 mb-1">Duration</p>
          <p className="text-sm font-semibold text-zinc-200">{formatDuration(log.duration_seconds)}</p>
        </div>
        <div className="px-4 py-3 text-center">
          <p className="text-[9px] font-bold tracking-widest uppercase text-zinc-600 mb-1">Cost</p>
          <p className="text-sm font-semibold text-zinc-200">{formatCost(log.cost_usd)}</p>
        </div>
        <div className="px-4 py-3 text-center">
          <p className="text-[9px] font-bold tracking-widest uppercase text-zinc-600 mb-1">Sentiment</p>
          <div className="flex items-center justify-center gap-1.5">
            <span className={cn('h-1.5 w-1.5 rounded-full', SENTIMENT_DOT[log.sentiment] ?? 'bg-zinc-500')} />
            <p className={cn('text-sm font-semibold', {
              'text-emerald-400': log.sentiment === 'Positive',
              'text-yellow-400': log.sentiment === 'Neutral',
              'text-red-400': log.sentiment === 'Negative',
            })}>{log.sentiment}</p>
          </div>
        </div>
      </div>

      {/* Transcript */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 min-h-0">
        {lines.length > 0 ? (
          lines.map((line, i) => (
            <div key={i} className={cn('flex gap-3', line.role === 'USER' && 'flex-row-reverse')}>
              <span className={cn(
                'text-[10px] font-bold tracking-wider flex-shrink-0 mt-1',
                line.role === 'AI' ? 'text-indigo-400' : 'text-zinc-500',
              )}>
                {line.role === 'AI' ? 'AI' : 'You'}
              </span>
              <div className={cn(
                'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
                line.role === 'AI'
                  ? 'bg-zinc-800/60 text-zinc-200 rounded-tl-sm'
                  : 'bg-indigo-600/15 border border-indigo-600/20 text-zinc-300 rounded-tr-sm',
              )}>
                {line.text}
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-zinc-600 italic">{log.transcript || 'No transcript available.'}</p>
        )}
      </div>

      {/* Outcome / Meeting booked banner */}
      {isMeetingBooked ? (
        <div className="m-4 flex-shrink-0 flex items-center justify-center gap-3 bg-emerald-600/10 border border-emerald-600/30 rounded-xl py-4">
          <CheckCircle2 size={18} className="text-emerald-400" />
          <span className="text-sm font-bold tracking-widest uppercase text-emerald-400">Meeting Booked</span>
        </div>
      ) : (
        <div className="px-5 py-3 border-t border-zinc-800 flex-shrink-0">
          <p className="text-xs text-zinc-600 mb-1">Outcome</p>
          <p className="text-sm text-zinc-300">{log.outcome || '-'}</p>
        </div>
      )}
    </div>
  )
}

export function Logs() {
  const [selected, setSelected] = useState<{ log: CallLog; index: number } | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const queryClient = useQueryClient()

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['callLogs'],
    queryFn: api.getCallLogs,
    refetchInterval: 15000,
  })

  const deleteMutation = useMutation({
    mutationFn: (logId: string) => api.deleteCallLog(logId),
    onSuccess: (_, logId) => {
      if (selected?.log.id === logId) setSelected(null)
      setConfirmDeleteId(null)
      void queryClient.invalidateQueries({ queryKey: ['callLogs'] })
    },
    onError: () => {
      toast.error('Failed to delete log.')
      setConfirmDeleteId(null)
    },
  })

  // Sort newest first
  const sorted = [...logs].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())

  const filtered = sorted.filter(
    (l) =>
      l.agent_name.toLowerCase().includes(search.toLowerCase()) ||
      l.phone_number.includes(search),
  )

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleSearch = (v: string) => {
    setSearch(v)
    setPage(1)
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* Main table panel */}
      <div className={cn('flex-1 flex flex-col overflow-hidden min-w-0', selected && 'border-r border-zinc-800')}>
        <div className="p-6 border-b border-zinc-800 flex-shrink-0">
          <h1 className="text-xl font-bold text-zinc-100">Call Logs</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Review past calls, transcripts, and outcomes.</p>
        </div>

        <div className="px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              type="text"
              placeholder="Search by number or agent..."
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-4 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {isLoading && (
            <div className="p-6 space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 bg-zinc-900 border border-zinc-800 rounded-xl animate-pulse" />
              ))}
            </div>
          )}

          {!isLoading && logs.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="w-14 h-14 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-4">
                <List size={22} className="text-zinc-600" />
              </div>
              <p className="text-zinc-400 font-medium">No calls yet</p>
              <p className="text-zinc-600 text-sm mt-1">Trigger a call from the Builder to see logs here.</p>
            </div>
          )}

          {!isLoading && logs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {['#', 'Agent', 'Phone', 'Date', 'Duration'].map((h) => (
                    <th key={h} className="text-left px-6 py-3 text-xs font-semibold text-zinc-600 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paginated.map((log, i) => {
                  const globalIndex = (page - 1) * PAGE_SIZE + i
                  const isConfirming = confirmDeleteId === log.id
                  return (
                    <tr
                      key={log.id}
                      onClick={() => { if (!isConfirming) setSelected({ log, index: globalIndex }) }}
                      className={cn(
                        'border-b border-zinc-800/50 last:border-0 cursor-pointer transition-colors group',
                        log.is_failed
                          ? selected?.log.id === log.id
                            ? 'bg-red-500/10 border-l-2 border-l-red-500'
                            : 'bg-red-500/5 border-l-2 border-l-red-500 hover:bg-red-500/10'
                          : selected?.log.id === log.id
                            ? 'bg-indigo-600/5 border-l-2 border-l-indigo-600'
                            : 'hover:bg-zinc-800/30',
                      )}
                    >
                      <td className="px-6 py-4 text-zinc-600 font-mono text-xs">{globalIndex + 1}</td>
                      <td className={cn('px-6 py-4 font-medium', log.is_failed ? 'text-red-300' : 'text-zinc-200')}>{log.agent_name}</td>
                      <td className={cn('px-6 py-4 font-mono text-xs', log.is_failed ? 'text-red-400/80' : 'text-zinc-400')}>{log.phone_number}</td>
                      <td className="px-6 py-4 text-zinc-400">
                        {new Date(log.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </td>
                      <td className={cn('px-6 py-4', log.is_failed ? 'text-red-400' : 'text-zinc-400')}>
                        <span className="inline-flex items-center gap-2">
                          {formatDuration(log.duration_seconds)}
                          {log.is_failed && (
                            <span className="text-[9px] font-bold tracking-wider uppercase text-red-400 bg-red-500/10 border border-red-500/30 rounded px-1.5 py-0.5">
                              Failed
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-right w-16">
                        {isConfirming ? (
                          <div className="flex items-center justify-end gap-2" onClick={e => e.stopPropagation()}>
                            <button
                              onClick={() => deleteMutation.mutate(log.id)}
                              disabled={deleteMutation.isPending}
                              className="text-xs font-semibold text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                            >
                              Delete
                            </button>
                            <button
                              onClick={() => setConfirmDeleteId(null)}
                              className="text-xs font-semibold text-zinc-500 hover:text-zinc-300 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={e => { e.stopPropagation(); setConfirmDeleteId(log.id) }}
                            className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-all p-1 rounded"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {!isLoading && totalPages > 1 && (
          <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-t border-zinc-800">
            <p className="text-xs text-zinc-600">
              {filtered.length} calls &bull; page {page} of {totalPages}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={15} />
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={cn(
                    'w-7 h-7 rounded-lg text-xs font-medium transition-colors',
                    p === page
                      ? 'bg-indigo-600 text-white'
                      : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300',
                  )}
                >
                  {p}
                </button>
              ))}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Inline transcript drawer - no overlay, side by side */}
      {selected && (
        <TranscriptDrawer
          log={selected.log}
          index={selected.index}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
