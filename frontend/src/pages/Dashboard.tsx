import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, Mic, ArrowRight, Trash2 } from 'lucide-react'
import { api } from '@/services/api'
import { formatCost, cn } from '@/lib/utils'
import { useAgentStore } from '@/store/agentStore'
import { useCallStore } from '@/store/callStore'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import type { Agent } from '@/types'

function useOpenAgent() {
  const navigate = useNavigate()
  const resetCall = useCallStore((s) => s.reset)
  const setSession = useAgentStore((s) => s.setSession)

  return (agent: Agent) => {
    resetCall()
    // Restore the original session ID so the backend finds the existing state
    // and edit requests work correctly instead of starting fresh
    const messages = agent.messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
    setSession(agent.id, agent.config, agent.vapi_assistant_id, messages)
    navigate('/builder')
  }
}


interface AgentCardProps {
  agent: Agent
  onOpen: () => void
  onDelete: () => void
}

function AgentCard({ agent, onOpen, onDelete }: AgentCardProps) {
  return (
    <div
      onClick={onOpen}
      className="group bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 flex flex-col gap-4 hover:border-zinc-700 hover:bg-zinc-900 transition-all cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-600/15 border border-indigo-600/25 flex items-center justify-center">
            <Mic size={16} className="text-indigo-400" />
          </div>
          <div>
            <h3 className="font-semibold text-zinc-100 text-sm leading-tight">{agent.name}</h3>
            <p className="text-xs text-zinc-600 mt-0.5 capitalize">{agent.config.voice_id}</p>
          </div>
        </div>
        <span className={cn(
          'text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-full border',
          agent.status === 'active'
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            : 'bg-zinc-800 text-zinc-500 border-zinc-700',
        )}>
          {agent.status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <StatCell
          label="Last Call"
          value={agent.last_call_at ? new Date(agent.last_call_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}
        />
        <StatCell
          label="Avg Cost"
          value={agent.avg_cost_usd !== null ? formatCost(agent.avg_cost_usd) : '-'}
        />
        <StatCell
          label="Book Rate"
          value={agent.success_rate !== null ? `${agent.success_rate}%` : '-'}
          valueClass={agent.success_rate !== null ? 'text-indigo-400' : undefined}
        />
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="p-1.5 rounded-lg text-zinc-700 hover:text-red-400 hover:bg-red-400/10 transition-all opacity-0 group-hover:opacity-100"
        >
          <Trash2 size={13} />
        </button>
        <div className="flex items-center text-xs text-zinc-600 group-hover:text-indigo-400 transition-colors">
          Open Builder <ArrowRight size={11} className="ml-1" />
        </div>
      </div>
    </div>
  )
}

interface StatCellProps {
  label: string
  value: string
  valueClass?: string
}

function StatCell({ label, value, valueClass }: StatCellProps) {
  return (
    <div>
      <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-0.5">{label}</p>
      <p className={cn('text-xs font-semibold text-zinc-300', valueClass)}>{value}</p>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-zinc-800" />
        <div className="space-y-2">
          <div className="h-3 w-28 bg-zinc-800 rounded" />
          <div className="h-2.5 w-16 bg-zinc-800 rounded" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
      </div>
    </div>
  )
}

export function Dashboard() {
  const navigate = useNavigate()
  const resetAgent = useAgentStore((s) => s.reset)
  const resetCall = useCallStore((s) => s.reset)
  const openAgent = useOpenAgent()
  const queryClient = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null)

  const startNewAgent = () => {
    resetAgent()
    resetCall()
    navigate('/builder')
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    await api.deleteAgent(deleteTarget.id)
    setDeleteTarget(null)
    queryClient.invalidateQueries({ queryKey: ['agents'] })
  }

  const { data: agents = [], isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: api.getAgents,
    refetchInterval: 10000,
  })

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Your Agents</h1>
          <p className="text-zinc-500 text-sm mt-1">
            {agents.length > 0 ? `${agents.length} agent${agents.length !== 1 ? 's' : ''} configured` : 'No agents yet'}
          </p>
        </div>
        <button
          onClick={startNewAgent}
          className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-500 transition-colors shadow-lg shadow-indigo-600/20"
        >
          <Plus size={15} />
          New Agent
        </button>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {!isLoading && agents.length === 0 && (
        <div className="flex flex-col items-center justify-center py-28 text-center">
          <div className="w-16 h-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-5">
            <Mic size={24} className="text-zinc-600" />
          </div>
          <p className="text-zinc-300 font-semibold text-lg">Build your first voice agent</p>
          <p className="text-zinc-600 text-sm mt-2 max-w-sm">
            Describe the agent you want in plain English. Ally will configure and deploy it.
          </p>
          <button
            onClick={startNewAgent}
            className="mt-6 flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-500 transition-colors"
          >
            <Plus size={15} />
            New Agent
          </button>
        </div>
      )}

      {!isLoading && agents.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} onOpen={() => openAgent(agent)} onDelete={() => setDeleteTarget(agent)} />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={`Delete "${deleteTarget?.name}"?`}
        description="This will permanently remove the agent and its Vapi configuration. This cannot be undone."
        confirmLabel="Delete Agent"
        dangerous
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
