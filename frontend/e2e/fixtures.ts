import type { Page, Route } from '@playwright/test'

export const MOCK_CONFIG = {
  name: 'Dan',
  first_message: "Hi, this is Dan from OziSurf! Do you have a couple of minutes?",
  system_prompt: "You are Dan from OziSurf, a friendly voice sales assistant.",
  voice_id: 'alloy',
  qualification_criteria: {
    questions: [
      "What is your current surfing level?",
      "What interests you most - lessons, vacation, or gear?",
      "When are you looking to get started?",
    ],
    disqualification_signals: [
      "Not interested",
      "Not in the target audience",
      "Already using a competing solution they're happy with",
      "No budget or timeline",
    ],
  },
  max_call_duration_seconds: 300,
}

export const MOCK_AGENT = {
  id: 'session-abc123',
  name: 'Dan',
  status: 'active',
  config: MOCK_CONFIG,
  vapi_assistant_id: 'vapi-assist-abc123',
  last_call_at: '2026-06-29T10:00:00Z',
  avg_latency_ms: 340,
  avg_cost_usd: 0.02,
  avg_sentiment: 'Positive',
  messages: [],
}

export const MOCK_CALL_LOG = {
  id: 'call-log-001',
  agent_name: 'Dan',
  phone_number: '+972-50-123-4567',
  date: '2026-06-29T10:00:00Z',
  duration_seconds: 154,
  sentiment: 'Positive',
  cost_usd: 0.04,
  outcome: 'Meeting booked for July 2026',
  transcript: 'AI: Hi, this is Dan from OziSurf! Do you have a couple of minutes?\nUSER: Sure, what is this about?\nAI: Great! I wanted to reach out about surf lessons. What is your current surfing level?\nUSER: I am a beginner.\nAI: Perfect! We have great beginner packages. Would you like to book a quick demo call?',
  latency_ms: 340,
}

// Mock all backend API routes
export async function mockAPI(page: Page) {
  // Health check
  await page.route('**/api/health', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        services: { anthropic: true, vapi: true, calcom: true, webhook: true },
      }),
    })
  })

  // Agents list
  await page.route('**/api/agents', (route: Route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([MOCK_AGENT]),
      })
    } else {
      route.continue()
    }
  })

  // Voice PATCH
  await page.route('**/api/agents/*/voice', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ voice_id: 'nova', config: { ...MOCK_CONFIG, voice_id: 'nova' } }),
    })
  })

  // Call logs
  await page.route('**/api/calls/logs', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_CALL_LOG]),
    })
  })

  // Trigger call
  await page.route('**/api/calls/trigger', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ call_id: 'call-xyz-001' }),
    })
  })
}

// Mock chat: initial build flow — needs more info first, then agent ready
export async function mockChatBuildFlow(page: Page) {
  let callCount = 0
  await page.route('**/api/chat', (route: Route) => {
    callCount++
    if (callCount === 1) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reply: "What is the target audience for your voice agent?",
          config: null,
          vapi_assistant_id: null,
        }),
      })
    } else {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reply: "Your agent is ready! You can now make a call.",
          config: MOCK_CONFIG,
          vapi_assistant_id: 'vapi-assist-abc123',
        }),
      })
    }
  })
}

// Mock chat: edit flow — always returns updated config
export async function mockChatEditFlow(page: Page, updatedConfig = MOCK_CONFIG) {
  await page.route('**/api/chat', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reply: "Done! Your agent has been updated.",
        config: updatedConfig,
        vapi_assistant_id: 'vapi-assist-abc123',
      }),
    })
  })
}

// Mock chat: no config returned (still gathering info)
export async function mockChatGathering(page: Page, reply: string) {
  await page.route('**/api/chat', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ reply, config: null, vapi_assistant_id: null }),
    })
  })
}

export async function sendChatMessage(page: Page, message: string) {
  const textarea = page.locator('textarea')
  await textarea.fill(message)
  await textarea.press('Enter')
}
