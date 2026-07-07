export interface QualificationCriteria {
  questions: string[]
  disqualification_signals: string[]
}

export interface VapiAssistantConfig {
  name: string
  first_message: string
  system_prompt: string
  voice_id: string
  qualification_criteria: QualificationCriteria
  max_call_duration_seconds: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  config?: VapiAssistantConfig
}

export type CallStatus = 'idle' | 'connecting' | 'in-progress' | 'retrying' | 'ended' | 'failed' | 'error'

export interface CallStatusEvent {
  // Backend forwards Vapi's raw dial-phase statuses in addition to our own CallStatus
  status: CallStatus | 'queued' | 'ringing'
  call_id?: string
  ended_reason?: string
  failure_message?: string | null
}

export interface CallLog {
  id: string
  vapi_call_id: string | null
  is_booked: boolean
  is_failed: boolean
  ended_reason?: string | null
  agent_name: string
  phone_number: string
  date: string
  duration_seconds: number
  sentiment: 'Positive' | 'Neutral' | 'Negative'
  cost_usd: number
  outcome: string
  transcript: string
  latency_ms: number | null
}

export interface Agent {
  id: string
  name: string
  status: 'active' | 'draft'
  config: VapiAssistantConfig
  vapi_assistant_id: string
  last_call_at: string | null
  avg_latency_ms: number | null
  avg_cost_usd: number | null
  avg_sentiment: string | null
  success_rate: number | null
  messages: { role: string; content: string }[]
}

export interface ChatRequest {
  message: string
  session_id: string
}

export interface ChatResponse {
  reply: string
  config: VapiAssistantConfig | null
  vapi_assistant_id: string | null
}
