import { Mic, Share2, Plus, AlertTriangle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { ChatPanel } from '@/components/ChatPanel'
import { AgentPreview } from '@/components/AgentPreview'
import { CallPanel } from '@/components/CallPanel'
import { useAgentStore } from '@/store/agentStore'
import { useCallStore } from '@/store/callStore'
import { api } from '@/services/api'

export function Builder() {
  const config = useAgentStore((s) => s.currentConfig)
  const vapiAssistantId = useAgentStore((s) => s.vapiAssistantId)
  const resetAgent = useAgentStore((s) => s.reset)
  const resetCall = useCallStore((s) => s.reset)

  const startNew = () => {
    resetAgent()
    resetCall()
  }

  // Detect stale store: we have a local config but the backend lost it (restart)
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: api.getAgents })
  const isStale = !!vapiAssistantId && agents.length > 0 &&
    !agents.find((a) => a.vapi_assistant_id === vapiAssistantId)
  const backendLost = !!vapiAssistantId && !isStale && agents.length === 0 &&
    agents !== undefined

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Left: Chat - full width until agent is created */}
      <div className={`min-w-0 border-r border-zinc-800 flex flex-col transition-all duration-500 ease-in-out ${config ? 'w-[45%]' : 'w-full'}`}>
        <ChatPanel />
      </div>

      {/* Right: Preview + Call - slides in when config is ready */}
      <div className={`min-w-0 flex flex-col overflow-hidden transition-all duration-500 ease-in-out ${config ? 'flex-1 opacity-100 translate-x-0' : 'w-0 opacity-0 translate-x-8 pointer-events-none'}`}>
        {/* Right panel header */}
        <div className="px-5 py-3 border-b border-zinc-800 flex items-center justify-between flex-shrink-0">
          {config ? (
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-6 h-6 rounded-lg bg-indigo-600 flex items-center justify-center flex-shrink-0">
                <Mic size={12} className="text-white" />
              </div>
              <span className="text-sm font-semibold text-zinc-100 truncate">{config.name}</span>
            </div>
          ) : (
            <h2 className="text-sm font-semibold text-zinc-500">Agent Preview</h2>
          )}
          <div className="flex items-center gap-2 flex-shrink-0">
            {config && (
              <button
                onClick={startNew}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-400 bg-zinc-800/60 border border-zinc-700 rounded-lg hover:bg-zinc-700 hover:text-zinc-200 transition-colors"
              >
                <Plus size={11} /> New Agent
              </button>
            )}
            {vapiAssistantId && (
              <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 transition-colors">
                <Share2 size={11} /> Publish
              </button>
            )}
          </div>
        </div>

        {backendLost && (
          <div className="mx-5 mt-4 flex items-center gap-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-4 py-2.5 text-xs text-yellow-400">
            <AlertTriangle size={13} className="flex-shrink-0" />
            Backend was restarted - this agent no longer exists on the server. Start a new agent or recreate it.
          </div>
        )}
        <AgentPreview />
        <CallPanel />
      </div>
    </div>
  )
}
