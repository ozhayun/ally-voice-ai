import { useRef, useEffect, useState, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAgentStore } from '@/store/agentStore'
import { useChat } from '@/hooks/useChat'

function TypingIndicator() {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500">✦ Ally AI</span>
      <div className="flex items-center gap-1 px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-2xl rounded-bl-sm w-fit">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  )
}

function formatContent(text: string): React.ReactNode {
  // Detect numbered list items like 1) 2) 3) — split before each one
  if (!/\d+\)\s/.test(text)) return text

  // Break before each numbered item, collapsing " and N)" connectors
  const lines = text
    .replace(/\s+(?:and\s+)?(?=\d+\)\s)/g, '\n')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)

  if (lines.length <= 1) return text

  return (
    <span className="flex flex-col gap-1.5">
      {lines.map((line, i) => (
        <span key={i}>{line}</span>
      ))}
    </span>
  )
}

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
}

function MessageBubble({ role, content }: MessageBubbleProps) {
  const isUser = role === 'user'
  return (
    <div className={cn('flex flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
      <span className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500">
        {isUser ? 'You' : '✦ Ally AI'}
      </span>
      <div
        dir="auto"
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed text-pretty',
          isUser
            ? 'bg-indigo-600 text-white rounded-tr-sm'
            : 'bg-zinc-900 border border-zinc-800 text-zinc-200 rounded-tl-sm',
        )}
      >
        {isUser ? content : formatContent(content)}
      </div>
    </div>
  )
}

export function ChatPanel() {
  const messages = useAgentStore((s) => s.messages)
  const chatMutation = useChat()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, chatMutation.isPending])

  const send = () => {
    const text = input.trim()
    if (!text || chatMutation.isPending) return
    setInput('')
    chatMutation.mutate(text)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const isEmpty = messages.length === 0 && !chatMutation.isPending

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100">Builder Chat</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-5 flex flex-col gap-4">
        {isEmpty && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-2">
              <div className="w-10 h-10 rounded-full bg-indigo-600/20 border border-indigo-600/30 flex items-center justify-center mx-auto">
                <span className="text-indigo-400 text-lg">✦</span>
              </div>
              <p className="text-zinc-400 text-sm font-medium">Describe your voice agent</p>
              <p className="text-zinc-600 text-xs">Tell me the goal, target audience, and what to ask.</p>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} role={msg.role} content={msg.content} />
        ))}
        {chatMutation.isPending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      <div className="px-4 py-3 border-t border-zinc-800">
        <div className="flex gap-2 items-end bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 focus-within:border-indigo-500 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Tell the builder to change voices, add logic, or refine scripts..."
            rows={1}
            dir="auto"
            className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-600 resize-none outline-none max-h-32"
            style={{ lineHeight: '1.5' }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || chatMutation.isPending}
            className="flex-shrink-0 p-1.5 rounded-lg bg-indigo-600 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-500 transition-colors"
          >
            <Send size={14} />
          </button>
        </div>
        <div className="flex items-center gap-4 mt-2 px-1">
          <button className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors">Attach context</button>
        </div>
      </div>
    </div>
  )
}
