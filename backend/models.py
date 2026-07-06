import re
from typing import Optional, TypedDict
from pydantic import BaseModel, EmailStr, field_validator


class QualificationCriteria(BaseModel):
    questions: list[str]
    disqualification_signals: list[str]


class VapiAssistantConfig(BaseModel):
    name: str
    first_message: str
    system_prompt: str
    voice_id: str
    qualification_criteria: QualificationCriteria
    max_call_duration_seconds: int = 300


class BuilderState(TypedDict):
    messages: list[dict]
    goal: Optional[str]
    target_audience: Optional[str]
    qualifying_questions: Optional[list[str]]
    disqualification_signals: Optional[list[str]]
    agent_name: Optional[str]
    company_name: Optional[str]
    first_message: Optional[str]
    voice_id: Optional[str]
    vapi_assistant_id: Optional[str]
    config: Optional[dict]
    needs_more_info: bool
    should_recompile: bool
    assistant_reply: str


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    reply: str
    config: Optional[VapiAssistantConfig] = None
    vapi_assistant_id: Optional[str] = None


class TriggerCallRequest(BaseModel):
    phone_number: str
    assistant_id: str
    lead_name: Optional[str] = None
    lead_email: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("phone_number must be E.164 format, e.g. +12125551234")
        return v

    @field_validator("lead_name", "lead_email", mode="before")
    @classmethod
    def sanitize_lead_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Strip newlines and control characters to prevent prompt injection
        sanitized = re.sub(r"[\r\n\t\x00-\x1f\x7f]", " ", str(v)).strip()
        return sanitized[:200]  # hard cap — no field needs more than 200 chars


class BookMeetingToolPayload(BaseModel):
    attendee_name: str
    attendee_email: EmailStr
    meeting_datetime_iso: str
    timezone: str
    title: Optional[str] = None


class CallLog(BaseModel):
    id: str
    agent_name: str
    phone_number: str
    date: str
    duration_seconds: int
    sentiment: str
    cost_usd: float
    outcome: str
    transcript: str
    latency_ms: Optional[float] = None
    vapi_call_id: Optional[str] = None
    is_booked: bool = False
    ended_reason: Optional[str] = None


class Agent(BaseModel):
    id: str
    name: str
    status: str
    config: VapiAssistantConfig
    vapi_assistant_id: str
    last_call_at: Optional[str] = None
    avg_latency_ms: Optional[float] = None
    avg_cost_usd: Optional[float] = None
    avg_sentiment: Optional[str] = None
    success_rate: Optional[float] = None  # percentage of calls that resulted in a booked meeting
    messages: list[dict] = []
