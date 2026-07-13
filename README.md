# Ally - Voice AI Builder

> **A personal project by Oz Hayun** · July 2026

---

## Executive Summary

Ally is a full-stack platform that lets a user describe a voice sales agent in plain language and have it operational - making real outbound phone calls, qualifying leads, and booking calendar meetings.

The user types a natural-language brief ("Call SaaS founders, ask if they have a growth team, book a demo"). Ally's LangGraph-powered builder asks clarifying questions, compiles a structured agent configuration, provisions a Vapi.ai voice assistant, and streams the result to the UI. From that point, a single click triggers an outbound call. The agent conducts the conversation autonomously, calls structured tool functions to qualify the lead and book a Cal.com slot, and the platform captures real metrics - cost, latency, sentiment, transcript - on every call.

**Stack:** React + Vite · FastAPI · LangGraph · Claude (via Instructor) · Vapi.ai · Cal.com · SQLite/SQLModel · SSE · ngrok

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                        Browser (React + Vite)                  │
│                                                                │
│   Builder Chat  ──SSE──▶  Agent Preview  ──────  Call Panel    │
│        │                                              │        │
└────────┼──────────────────────────────────────────────┼────────┘
         │ POST /api/chat                               │ POST /api/calls/trigger
         ▼                                             ▼
┌───────────────────────────────────────────────────────────────┐
│                        FastAPI (Python 3.11)                  │
│                                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │  /chat      │   │  /calls      │   │  /webhooks/vapi    │  │
│  │  router     │   │  router      │   │  (HMAC-verified)   │  │
│  └──────┬──────┘   └──────┬───────┘   └────────┬───────────┘  │
│         │                 │                     │             │
│         ▼                 ▼                     ▼             │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │  LangGraph  │   │  Vapi        │   │  SQLModel /        │  │
│  │  Builder    │   │  Service     │   │  SQLite            │  │
│  │  State      │   │  (overrides  │   │  (call logs,       │  │
│  │  Machine    │   │  + trigger)  │   │   agent state)     │  │
│  └──────┬──────┘   └──────┬───────┘   └────────────────────┘  │
│         │                 │                                   │
└─────────┼─────────────────┼─────────────────────────────────-─┘
          │                 │
          ▼                 ▼
   ┌─────────────┐   ┌──────────────────────────────────────────┐
   │  Anthropic  │   │                Vapi.ai                   │
   │  Claude     │   │                                          │
   │  (via       │   │  Voice Assistant ──▶ Outbound Call       │
   │  Instructor)│   │       │                                  │
   └─────────────┘   │       ▼                                  │
                     │  Tool Calls (qualify_lead, book_meeting) │
                     │       │                                  │
                     └───────┼──────────────────────────────────┘
                             │ POST /api/webhooks/vapi
                             ▼
                      ┌─────────────┐
                      │   Cal.com   │
                      │   REST v2   │
                      │  (booking)  │
                      └─────────────┘
```

### Request Flow - Builder

1. User message → `POST /api/chat` → **LangGraph** `gather_requirements` node (Claude via Instructor)
2. If requirements complete → `compile_config` node builds `VapiAssistantConfig` (Pydantic-validated)
3. `sync_to_vapi` node provisions/updates the Vapi assistant via REST API
4. State persisted to SQLite; `ChatResponse` streamed back to UI

### Request Flow - Call

1. `POST /api/calls/trigger` → system prompt refreshed with lead info (injected at top, sanitized)
2. Refreshed prompt sent as per-call `assistantOverrides` on `POST /call/phone` (no PATCH before dial)
3. Vapi calls the lead; agent speaks using Cartesia TTS + Deepgram STT
4. Tool calls (`qualify_lead`, `book_meeting`) POST to `/api/webhooks/vapi` (HMAC-verified when `VAPI_WEBHOOK_SECRET` is set)
5. `book_meeting` → Cal.com REST v2 → meeting confirmed
6. SSE streams call status with `endedReason` / `failure_message`; auto-redial once on `customer-did-not-answer`
7. `end-of-call-report` webhook → transcript analyzed by Claude → log persisted (`is_failed` for carrier failures)

---

## Key Architectural Decisions

- **LangGraph state machine** - The builder is not a simple chat loop. It has distinct phases: gathering requirements, compiling config, and syncing to Vapi. LangGraph makes these transitions explicit, deterministic, and inspectable. Conditional edges (`_route_after_gather`) prevent the model from advancing until requirements are genuinely satisfied, eliminating the hallucinated-config problem common in freeform LLM pipelines.

- **Vapi.ai for voice orchestration** - Vapi handles the hard parts of telephony: WebRTC/PSTN bridging, barge-in detection, STT/TTS latency optimization, and tool-call dispatch mid-conversation. Building this in-house would be weeks of work. Vapi's `assistantOverrides` and `endCallFunctionEnabled` interfaces gave enough control to implement the qualification and booking flows without coupling the platform to a specific telephony provider.

- **Anthropic Claude + Instructor for structured outputs** - All LLM interactions that produce structured data (agent config compilation, transcript sentiment analysis) go through `instructor` with Pydantic response models. This eliminates JSON parsing fragility entirely - if Claude can't produce a valid `VapiAssistantConfig`, the call fails loudly at the model layer, not silently downstream.

- **SQLModel + SQLite** - For a local-first MVP, SQLite with SQLModel gives full relational persistence (agent state, call logs, booking flags) with zero infrastructure. The schema is defined once in Python types; SQLModel handles migrations. Upgrading to PostgreSQL requires changing one connection string.

- **Server-Sent Events over WebSockets** - Call status streaming is unidirectional (server → client). SSE is sufficient, requires no handshake protocol, works through standard HTTP/2, and is natively supported by the browser `EventSource` API. The added complexity of WebSockets was not justified.

- **Cal.com REST API v2** - Cal.com v1 is decommissioned. v2 uses Bearer token auth and returns structured availability and booking objects. The integration is thin by design: Ally only needs `GET /slots` and `POST /bookings`.

- **Data Integrity and Validation** - Pydantic models are the single source of truth across the entire backend. Every payload from the LLM, every incoming webhook, and every API request is validated against a typed model before touching the database. This prevents inconsistent state and makes failures loud and early rather than silent and downstream.

---

## Security Hardening

The following security controls are in place:

| Vector                 | Control                                                                                                                                                                                         |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Prompt injection**   | `lead_name` and `lead_email` are sanitized before system prompt injection - newlines, carriage returns, and all ASCII control characters are stripped; fields are hard-capped at 200 characters |
| **Webhook spoofing**   | `/api/webhooks/vapi` verifies Vapi's HMAC-SHA256 signature via `hmac.compare_digest` (constant-time) when `VAPI_WEBHOOK_SECRET` is configured                                                   |
| **PII in logs**        | Trigger-call logs record `lead_provided=True/False` rather than actual name/email values                                                                                                        |
| **Error disclosure**   | Internal exceptions are logged server-side only; clients receive a generic `500` message                                                                                                        |
| **Input validation**   | `phone_number` is validated as strict E.164 format via a Pydantic `field_validator` before reaching Vapi                                                                                        |
| **Debug endpoint**     | `/api/webhooks/debug` is protected by `DEBUG_SECRET` when configured - unauthenticated access is blocked                                                                                        |
| **Dependency pinning** | All Python dependencies are pinned to exact versions in `requirements.txt` to eliminate supply-chain drift                                                                                      |
| **Secrets management** | No secrets committed - `.env` is gitignored; `.env.example` provides the full variable schema                                                                                                   |

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- [ngrok](https://ngrok.com) (required for Vapi webhooks)
- API keys: Anthropic, Vapi, Cal.com

### Step 1 - Configure environment

```bash
cd ally/backend
cp .env.example .env
# Open .env and fill in all API keys
```

| Variable                    | Source                                                        |
| --------------------------- | ------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`         | [console.anthropic.com](https://console.anthropic.com)        |
| `VAPI_API_KEY`              | Vapi dashboard → API Keys                                     |
| `VAPI_INTL_PHONE_NUMBER_ID` | Vapi dashboard → Phone Numbers (Twilio-backed, for +972 etc.) |
| `VAPI_PHONE_NUMBER_IDS`     | Comma-separated Vapi free number UUIDs (US pool)              |
| `VAPI_PHONE_NUMBERS`        | Matching display strings for the pool above                   |
| `CALCOM_API_KEY`            | Cal.com → Settings → API Keys                                 |
| `CALCOM_EVENT_TYPE_ID`      | Cal.com → Event Types → numeric ID from URL                   |
| `WEBHOOK_BASE_URL`          | Your ngrok `https://` URL (see Step 3)                        |

### Step 2 - Install dependencies

```bash
# Backend
cd ally/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ally/frontend
npm install
```

### Step 3 - Run

Open three terminal tabs:

```bash
# Tab 1 - ngrok tunnel (paste the https URL into .env as WEBHOOK_BASE_URL, then restart backend)
ngrok http 8000

# Tab 2 - Backend
cd ally/backend && source venv/bin/activate
uvicorn main:app --reload --port 8000

# Tab 3 - Frontend
cd ally/frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Demo

A video walkthrough of the full end-to-end flow - agent creation, live outbound call, lead qualification, and Cal.com booking - is available here:

**[▶ Watch Demo](https://www.youtube.com/watch?v=kXYloRju5Ys)**

The demo covers:

- Describing an agent in natural language and watching the builder configure it in real time
- Triggering an outbound call with pre-filled lead info
- The agent qualifying the lead through structured questions
- A Cal.com meeting being booked mid-call and appearing in the dashboard
- Call Logs showing real cost, latency, sentiment, and full transcript

---

## Project Structure

```
ally/
├── backend/
│   ├── main.py               # FastAPI app, lifespan, middleware
│   ├── config.py             # Pydantic settings from .env
│   ├── models.py             # All Pydantic + TypedDict models
│   ├── database.py           # SQLModel schema + CRUD
│   ├── routers/
│   │   ├── chat.py           # POST /chat - builder entry point
│   │   ├── agents.py         # GET/DELETE/PATCH /agents
│   │   ├── calls.py          # POST /calls/trigger, GET /calls/logs, SSE status
│   │   └── webhooks.py       # POST /webhooks/vapi (HMAC-verified)
│   └── services/
│       ├── builder.py        # LangGraph state machine
│       ├── vapi.py           # Vapi REST client
│       └── calcom.py         # Cal.com REST v2 client
└── frontend/
    └── src/
        ├── pages/            # Dashboard, Builder, Logs
        ├── components/       # ChatPanel, AgentPreview, CallPanel
        ├── store/            # Zustand (UI state)
        ├── hooks/            # useCallStatus (SSE)
        └── services/         # api.ts (axios)
```
