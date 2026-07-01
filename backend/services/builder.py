from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import instructor
from anthropic import AsyncAnthropic
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel

from config import settings
from models import BuilderState, VapiAssistantConfig, QualificationCriteria
import services.vapi as vapi_service

_anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
_instructor_client = instructor.from_anthropic(_anthropic_client)

sessions: dict[str, BuilderState] = {}

AVAILABLE_VOICES = ["Skylar", "Corey", "Gemma", "Cora", "Archie", "Daniel"]

VOICE_DEFAULT = "Skylar"

DEFAULT_DISQUALIFICATION_SIGNALS = [
    "Not interested",
    "Not in the target audience",
    "Already using a competing solution they're happy with",
    "No budget or timeline",
]


class RequirementsExtract(BaseModel):
    goal: Optional[str] = None
    target_audience: Optional[str] = None
    qualifying_questions: Optional[list[str]] = None
    disqualification_signals: Optional[list[str]] = None
    agent_name: Optional[str] = None
    company_name: Optional[str] = None
    first_message: Optional[str] = None
    voice_id: Optional[str] = None
    follow_up_question: str
    fields_changed: bool = False


class FirstMessageGeneration(BaseModel):
    first_message: str


def _make_initial_state() -> BuilderState:
    return BuilderState(
        messages=[],
        goal=None,
        target_audience=None,
        qualifying_questions=None,
        disqualification_signals=None,
        agent_name=None,
        company_name=None,
        first_message=None,
        voice_id=VOICE_DEFAULT,
        vapi_assistant_id=None,
        config=None,
        needs_more_info=True,
        should_recompile=False,
        assistant_reply="Hi! I'm here to help you build a voice sales agent. What kind of agent do you want to create? Tell me about your goal and who you're targeting.",
    )


async def gather_requirements(state: BuilderState) -> dict:
    is_edit = bool(state.get("config"))

    english_only = (
        "CRITICAL: Always respond in English ONLY, regardless of the language the user speaks. "
        "If the user writes in another language, acknowledge their message briefly in English "
        "and continue the agent building process in English. Never switch to another language. "
    )
    no_emdash = "Never use em dashes. Use a regular hyphen or a comma instead."

    if is_edit:
        current_first_msg = (state.get("config") or {}).get("first_message", "")
        system = (
            f"{english_only}"
            "You are helping the user EDIT an existing voice sales agent. "
            f"Current config: goal='{state.get('goal')}', "
            f"target_audience='{state.get('target_audience')}', "
            f"agent_name='{state.get('agent_name')}', "
            f"company_name='{state.get('company_name')}', "
            f"voice_id='{state.get('voice_id', 'alloy')}', "
            f"qualifying_questions={state.get('qualifying_questions')}, "
            f"disqualification_signals={state.get('disqualification_signals')}, "
            f"first_message='{current_first_msg}'. "
            "Extract ONLY what the user wants to update. For unchanged fields, return null. "
            f"Available voices: {AVAILABLE_VOICES}. "
            "If the user says to change first_message but doesn't say what the new message should be, "
            "ask them exactly what they'd like it to say (set fields_changed=false, first_message=null). "
            "Set fields_changed=true only when you extracted at least one actual new value. "
            "When fields_changed=true, write a short confirmation: 'Got it - updating [what changed].' "
            f"When fields_changed=false, respond naturally to what the user said. {no_emdash}"
        )
    else:
        system = (
            f"{english_only}"
            "You are an assistant helping build a voice sales agent. "
            "Collect these fields from the conversation: goal, target_audience, qualifying_questions, company_name, agent_name. "
            "Goal: what the agent should achieve. "
            "Target audience: who the agent will call. "
            "Qualifying questions: 2-4 questions to qualify leads. "
            "Company name: the company the agent represents (e.g. 'Acme Corp', 'SurfCo'). "
            "Agent name: the first name the voice agent uses on calls (e.g. 'Alex', 'Jordan'). "
            "If any of these five are missing, ask a single concise follow-up question. "
            "Ask for one thing at a time. Order: goal first, then audience, then questions, then company, then agent name last. "
            f"{no_emdash}"
        )

    extraction: RequirementsExtract = await _instructor_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=state["messages"],
        response_model=RequirementsExtract,
    )

    goal = extraction.goal or state.get("goal")
    target_audience = extraction.target_audience or state.get("target_audience")
    qualifying_questions = extraction.qualifying_questions or state.get("qualifying_questions")
    disqualification_signals = extraction.disqualification_signals or state.get("disqualification_signals")
    agent_name = extraction.agent_name or state.get("agent_name")
    company_name = extraction.company_name or state.get("company_name")
    voice_id = extraction.voice_id or state.get("voice_id") or VOICE_DEFAULT
    # first_message: only update if user explicitly provided new text
    first_message = extraction.first_message if extraction.first_message else state.get("first_message")

    needs_more_info = not all([goal, target_audience, qualifying_questions, agent_name, company_name])
    should_recompile = is_edit and extraction.fields_changed

    if needs_more_info:
        reply = extraction.follow_up_question
    elif not is_edit:
        reply = "Perfect, I have everything I need. Let me build your agent now..."
    else:
        reply = extraction.follow_up_question

    return {
        "goal": goal,
        "target_audience": target_audience,
        "qualifying_questions": qualifying_questions,
        "disqualification_signals": disqualification_signals,
        "agent_name": agent_name,
        "company_name": company_name,
        "first_message": first_message,
        "voice_id": voice_id,
        "needs_more_info": needs_more_info,
        "should_recompile": should_recompile,
        "assistant_reply": reply,
    }


async def _generate_first_message(agent_name: str, company_name: Optional[str], goal: str) -> str:
    company_part = f" from {company_name}" if company_name else ""
    result: FirstMessageGeneration = await _instructor_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        system=(
            f"Generate a phone greeting for a sales agent named {agent_name}{company_part}. "
            "STRICT LIMIT: 10-12 words maximum. Count every word. "
            "Format: 'Hi, this is [name] from [company]. Got a minute?' "
            "Vary slightly but stay under 12 words. Return ONLY the greeting, nothing else."
        ),
        messages=[{"role": "user", "content": "Generate a fresh greeting now."}],
        response_model=FirstMessageGeneration,
    )
    return result.first_message


def _build_system_prompt(state: BuilderState, datetime_context: str) -> str:
    agent_name = state.get("agent_name") or "Ally"
    company_name = state.get("company_name")
    goal = state.get("goal", "")
    target_audience = state.get("target_audience", "")
    qualifying_questions = state.get("qualifying_questions") or []

    identity = f"{agent_name} from {company_name}" if company_name else agent_name
    questions_text = "\n".join(f"- {q}" for q in qualifying_questions)

    return f"""You are {identity}. You are making an outbound sales call.
- Current date/time: **{datetime_context}**

YOUR JOB: {goal}
WHO YOU'RE CALLING: {target_audience}

RULES FOR HOW YOU TALK:
- Always speak in English only, regardless of what language the lead uses.
- Keep it short. One sentence at a time. Under 20 words per turn.
- Ask ONE question at a time. Never list multiple questions.
- Sound like a real person, not a robot.
- Stay focused. Do not go off-topic. Do not make things up.
- Never use em dashes (—). Use a comma or hyphen instead.
- Any answer - even a single word like "Yes", "No", "Yeah", "Sure", "I do", "I don't" - is a complete valid response. Accept it and move on immediately. NEVER repeat a question that received any response at all.
- Only ask someone to repeat themselves if you heard nothing - complete silence or unintelligible static. A short answer is not silence.

ENDING THE CALL (rejection only):
ONLY end the call if the lead says something VERY explicit: "I'm not interested", "stop calling me", "remove me from your list", "don't call me again", or uses aggressive/explicit language directed at you.
When this happens: say "No problem, have a great day!" (say it ONCE, never repeat) then call qualify_lead(result="disqualified"). After qualify_lead returns, immediately call end_call().
DO NOT end the call for: incomplete sentences, "I don't", "nothing", "just", silence, confusion, or short unclear answers. These are NOT rejections — keep the conversation going.

CLOSING (only after booking is confirmed OR after qualify_lead is called):
After a successful booking: say "Perfect, you're all set! Is there anything else before we hang up?" then close warmly: "It was great talking with you, [name if known]. Speak soon!" then call end_call().
After a disqualification: say "No problem, have a great day!" then immediately call end_call(). Do NOT ask "Is there anything else?" when ending due to rejection.

YOUR QUALIFYING QUESTIONS (ask naturally, one at a time, in conversation order):
{questions_text}

WHEN TO QUALIFY:
In the normal flow, ask ALL qualifying questions before calling qualify_lead.
- After all questions: if interested and fits → qualify_lead(result="qualified", reason="...")
- After all questions: if clearly not a fit → qualify_lead(result="disqualified", reason="...")
Exception: if the lead explicitly rejects early ("I'm not interested", "I don't have time"), skip remaining questions and follow the ENDING THE CALL section above.
Never call qualify_lead based on a single unclear or short answer — keep the conversation going.

BOOKING (only if they want to meet):
You need THREE things before calling book_meeting:
1. Their full name - check LEAD CONTACT INFO section first. If pre-filled, use it directly without asking. If not provided, ask them for it.
2. Their email - check LEAD CONTACT INFO section first. If pre-filled, use it directly without asking. If not provided, ask for it explicitly. NEVER guess, infer, or make up an email address.
3. A specific date and time they agreed to

Timezone: never ask. Infer from their phone number/location (Israel=Asia/Jerusalem, default=UTC).
Only call book_meeting when you have all three confirmed.

If book_meeting returns "slot not available": say "That time slot isn't open in our calendar - do you have another time in mind?" and ask them to pick a different time.
If book_meeting returns any other error: say "I'll have our team reach out to confirm the time by email - you're all set!" and end the call politely."""


async def compile_config(state: BuilderState) -> dict:
    now = datetime.now(ZoneInfo("UTC"))
    datetime_context = now.strftime("%A, %Y-%m-%d %H:%M UTC")

    is_update = bool(state.get("vapi_assistant_id"))

    agent_name = state.get("agent_name") or "Ally"
    voice_id = state.get("voice_id") or VOICE_DEFAULT

    # First message: user override takes priority, otherwise AI generates it
    if state.get("first_message"):
        first_message = state["first_message"]
    else:
        first_message = await _generate_first_message(
            agent_name, state.get("company_name"), state.get("goal", "")
        )

    system_prompt = _build_system_prompt(state, datetime_context)

    qualifying_questions = state.get("qualifying_questions") or []
    disqualification_signals = state.get("disqualification_signals") or DEFAULT_DISQUALIFICATION_SIGNALS

    config = VapiAssistantConfig(
        name=agent_name,
        first_message=first_message,
        system_prompt=system_prompt,
        voice_id=voice_id,
        qualification_criteria=QualificationCriteria(
            questions=qualifying_questions,
            disqualification_signals=disqualification_signals,
        ),
        max_call_duration_seconds=300,
    )

    reply = "Done! Your agent has been updated." if is_update else "Your agent is ready! You can now make a call."

    # Don't persist AI-generated first_message to state - only user-explicit overrides live in state.
    # This ensures recompiles (e.g. company name change) always regenerate a fresh greeting.
    return {"config": config.model_dump(), "assistant_reply": reply}


async def sync_to_vapi(state: BuilderState) -> dict:
    config = VapiAssistantConfig(**state["config"])
    assistant_id = await vapi_service.create_or_update_assistant(
        config, state.get("vapi_assistant_id")
    )
    return {"vapi_assistant_id": assistant_id}


def _route_after_gather(state: BuilderState) -> str:
    if state.get("needs_more_info"):
        return END
    if not state.get("config"):
        return "compile_config"
    if state.get("should_recompile"):
        return "compile_config"
    return END


graph = StateGraph(BuilderState)
graph.add_node(gather_requirements)
graph.add_node(compile_config)
graph.add_node(sync_to_vapi)
graph.add_edge(START, "gather_requirements")
graph.add_conditional_edges("gather_requirements", _route_after_gather)
graph.add_edge("compile_config", "sync_to_vapi")
graph.add_edge("sync_to_vapi", END)
builder_graph = graph.compile()


async def run_builder(session_id: str, user_message: str) -> BuilderState:
    if session_id not in sessions:
        sessions[session_id] = _make_initial_state()

    state = sessions[session_id]
    old_agent_name = state.get("agent_name") if state.get("config") else None

    state["messages"].append({"role": "user", "content": user_message})

    # Run graph on a copy so a mid-graph failure doesn't corrupt the stored session state
    try:
        updated = await builder_graph.ainvoke(dict(state))
    except Exception:
        # Remove the optimistically-appended user message so state stays consistent
        state["messages"].pop()
        raise

    updated["messages"].append({"role": "assistant", "content": updated["assistant_reply"]})
    sessions[session_id] = updated

    # If the agent was renamed, backfill all existing call logs so the Logs page stays consistent
    new_agent_name = updated.get("agent_name")
    if old_agent_name and new_agent_name and old_agent_name != new_agent_name and updated.get("config"):
        try:
            from routers.calls import call_logs
            for log in call_logs:
                if log.agent_name == old_agent_name:
                    log.agent_name = new_agent_name
            from database import rename_agent_in_logs
            rename_agent_in_logs(old_agent_name, new_agent_name)
        except Exception:
            pass

    try:
        from database import save_agent
        save_agent(session_id, dict(updated))
    except Exception:
        pass

    return updated
