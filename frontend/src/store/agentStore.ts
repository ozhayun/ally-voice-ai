import { create } from 'zustand'
import { v4 as uuid } from 'uuid'
import type { VapiAssistantConfig, ChatMessage } from '@/types'

type AgentStoreState = {
  sessionId: string
  messages: ChatMessage[]
  currentConfig: VapiAssistantConfig | null
  vapiAssistantId: string | null
}

type AgentStoreActions = {
  setConfig: (config: VapiAssistantConfig, id: string) => void
  setSession: (sessionId: string, config: VapiAssistantConfig, vapiAssistantId: string, messages: ChatMessage[]) => void
  addMessage: (msg: ChatMessage) => void
  reset: () => void
}

type AgentStore = AgentStoreState & AgentStoreActions

export const useAgentStore = create<AgentStore>()((set) => ({
  sessionId: uuid(),
  messages: [],
  currentConfig: null,
  vapiAssistantId: null,

  setConfig: (config, id) => set({ currentConfig: config, vapiAssistantId: id }),
  setSession: (sessionId, config, vapiAssistantId, messages) =>
    set({ sessionId, currentConfig: config, vapiAssistantId, messages }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  reset: () =>
    set({
      sessionId: uuid(),
      messages: [],
      currentConfig: null,
      vapiAssistantId: null,
    }),
}))
