import axios from 'axios'
import type { ChatResponse, Agent, CallLog, VapiAssistantConfig } from '@/types'

const client = axios.create({ baseURL: '/api' })

export const api = {
  sendMessage: (message: string, sessionId: string): Promise<ChatResponse> =>
    client.post<ChatResponse>('/chat', { message, session_id: sessionId }).then(r => r.data),

  getAgents: (): Promise<Agent[]> =>
    client.get<Agent[]>('/agents').then(r => r.data),

  triggerCall: (
    phoneNumber: string,
    assistantId: string,
    leadName?: string,
    leadEmail?: string,
  ): Promise<{ call_id: string; caller_number: string; pool_index: number; pool_size: number }> =>
    client.post<{ call_id: string; caller_number: string; pool_index: number; pool_size: number }>('/calls/trigger', {
      phone_number: phoneNumber,
      assistant_id: assistantId,
      lead_name: leadName || undefined,
      lead_email: leadEmail || undefined,
    }).then(r => r.data),

  getCallLogs: (): Promise<CallLog[]> =>
    client.get<CallLog[]>('/calls/logs').then(r => r.data),

  updateVoice: (sessionId: string, voiceId: string): Promise<{ voice_id: string; config: VapiAssistantConfig }> =>
    client.patch<{ voice_id: string; config: VapiAssistantConfig }>(`/agents/${sessionId}/voice`, { voice_id: voiceId }).then(r => r.data),

  syncCallLog: (callId: string): Promise<{ synced: boolean }> =>
    client.post<{ synced: boolean }>(`/calls/sync/${callId}`).then(r => r.data),

  endCall: (callId: string): Promise<{ ok: boolean }> =>
    client.post<{ ok: boolean }>(`/calls/${callId}/end`).then(r => r.data),

  deleteAgent: (sessionId: string): Promise<{ deleted: string }> =>
    client.delete<{ deleted: string }>(`/agents/${sessionId}`).then(r => r.data),

  deleteCallLog: (logId: string): Promise<{ deleted: string }> =>
    client.delete<{ deleted: string }>(`/calls/logs/${logId}`).then(r => r.data),
}
