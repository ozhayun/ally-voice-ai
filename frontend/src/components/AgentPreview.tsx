import { useState, useRef, useEffect } from 'react'
import { ChevronDown, ChevronUp, Mic, CheckCircle2, AlertCircle } from 'lucide-react'
import { useAgentStore } from '@/store/agentStore'
import { api } from '@/services/api'

const VOICES = [
  { id: 'Skylar', label: 'Skylar', gender: 'F' },
  { id: 'Gemma', label: 'Gemma', gender: 'F' },
  { id: 'Cora', label: 'Cora', gender: 'F' },
  { id: 'Corey', label: 'Corey', gender: 'M' },
  { id: 'Archie', label: 'Archie', gender: 'M' },
  { id: 'Daniel', label: 'Daniel', gender: 'M' },
] as const

export function AgentPreview() {
  const config = useAgentStore((s) => s.currentConfig)
  const sessionId = useAgentStore((s) => s.sessionId)
  const setConfig = useAgentStore((s) => s.setConfig)
  const vapiAssistantId = useAgentStore((s) => s.vapiAssistantId)
  const [promptExpanded, setPromptExpanded] = useState(false)
  const [voiceUpdating, setVoiceUpdating] = useState(false)
  const [voiceDropdownOpen, setVoiceDropdownOpen] = useState(false)
  const voiceDropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (voiceDropdownRef.current && !voiceDropdownRef.current.contains(e.target as Node)) {
        setVoiceDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  async function handleVoiceChange(voiceId: string) {
    if (!vapiAssistantId || voiceUpdating) return
    setVoiceUpdating(true)
    try {
      const res = await api.updateVoice(sessionId, voiceId)
      setConfig(res.config, vapiAssistantId)
    } catch {
      // silently ignore - voice stays as-is
    } finally {
      setVoiceUpdating(false)
    }
  }

  if (!config) {
    return (
      <div className="flex-1 flex items-center justify-center text-center p-6">
        <div className="space-y-3">
          <div className="w-12 h-12 rounded-full bg-zinc-800/60 border border-zinc-700/50 flex items-center justify-center mx-auto">
            <Mic size={20} className="text-zinc-600" />
          </div>
          <p className="text-zinc-500 text-sm">Chat with Ally to generate your agent.</p>
          <p className="text-zinc-700 text-xs">Preview will appear here once configured.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-4 animate-in fade-in duration-500">
      {/* Agent header */}
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-zinc-100">{config.name}</h3>
        <div className="flex items-center gap-1.5 shrink-0" ref={voiceDropdownRef}>
          <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-semibold">Voice</span>
          <div className="relative">
            <button
              onClick={() => !voiceUpdating && setVoiceDropdownOpen(v => !v)}
              disabled={voiceUpdating}
              className="flex items-center gap-1 text-xs text-zinc-300 bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 hover:border-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
            >
              {VOICES.find(v => v.id === config.voice_id)?.label ?? 'Skylar'}
              <ChevronDown size={10} className="text-zinc-500" />
            </button>
            {voiceDropdownOpen && (
              <div className="absolute right-0 top-full mt-1 bg-zinc-900 border border-zinc-700 rounded-lg overflow-hidden z-50 min-w-[190px] shadow-xl">
                {VOICES.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => { handleVoiceChange(v.id); setVoiceDropdownOpen(false) }}
                    className={`w-full text-left px-3 py-2 text-xs transition-colors hover:bg-zinc-800 ${v.id === config.voice_id ? 'text-indigo-400' : 'text-zinc-300'}`}
                  >
                    {v.label} <span className="text-zinc-600 ml-1">{v.gender === 'F' ? '♀' : '♂'}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* First message + qualifying questions: two column */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500 mb-2">First Message</p>
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-3 h-full">
            <p className="text-sm text-zinc-300 leading-relaxed">
              &ldquo;{config.first_message}&rdquo;
            </p>
          </div>
        </div>
        <div>
          <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500 mb-2">Qualifying Questions</p>
          <ul className="space-y-2">
            {config.qualification_criteria.questions.map((q, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle2 size={14} className="text-indigo-400 mt-0.5 flex-shrink-0" />
                <span className="text-sm text-zinc-300 leading-tight">{q}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Disqualification signals */}
      {config.qualification_criteria.disqualification_signals.length > 0 && (
        <div  className="mt-10">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500 mb-2">Disqualification Signals</p>
          <ul className="space-y-1.5">
            {config.qualification_criteria.disqualification_signals.map((s, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-zinc-400">
                <AlertCircle size={13} className="text-red-400 flex-shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* System prompt expandable */}
      <div className="border border-zinc-800 rounded-xl overflow-hidden">
        <button
          onClick={() => setPromptExpanded((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 text-xs text-zinc-400 hover:text-zinc-200 font-medium transition-colors hover:bg-zinc-800/30"
        >
          <span>System Prompt (Full)</span>
          {promptExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
        {promptExpanded && (
          <div className="px-4 pb-4 border-t border-zinc-800 bg-zinc-950/50">
            <p className="text-xs text-zinc-400 leading-relaxed font-mono whitespace-pre-wrap mt-3">
              {config.system_prompt}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
