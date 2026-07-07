import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models import TriggerCallRequest, CallLog
import services.vapi as vapi_service
import services.builder as builder_service

logger = logging.getLogger("calls")
router = APIRouter()

# In-memory list kept in sync with DB - loaded on startup via main.py lifespan
call_logs: list[CallLog] = []

# Guards against concurrent duplicate log creation (webhook + SSE arriving at the same time)
_creating_log_for: set[str] = set()

# call_id → original trigger request + attempt number, so the SSE stream can auto-redial
# once when the carrier drops the answer signal (endedReason=customer-did-not-answer)
_call_attempts: dict[str, dict] = {}
MAX_CALL_ATTEMPTS = 2


# endedReasons that always mean the call never became a conversation
HARD_FAILURE_REASONS = {
    "customer-did-not-answer": (
        "Failed — the carrier never reported the call as answered, so the agent was never "
        "connected. The lead may have picked up into dead air. Retrying usually works."
    ),
    "customer-busy": "Failed — the line was busy.",
    "twilio-failed-to-connect-call": "Failed — Twilio could not connect the call.",
}
DEAD_AIR_MESSAGE = (
    "Failed — the call connected but the audio path was dead: the agent's greeting was cut off "
    "and the caller was never heard. Carrier/media issue, not the agent."
)


def classify_failure(ended_reason: str, transcript: str) -> Optional[str]:
    """Returns a human-readable failure message, or None if the call was a real conversation.
    silence-timed-out only counts as a failure when the caller was never transcribed —
    a normal conversation can also end by silence."""
    if not ended_reason:
        return None
    if ended_reason in HARD_FAILURE_REASONS:
        return HARD_FAILURE_REASONS[ended_reason]
    if ended_reason.startswith("call.start.error"):
        return f"Failed — the call could not be started ({ended_reason})."
    if ended_reason == "silence-timed-out" and "User:" not in (transcript or ""):
        return DEAD_AIR_MESSAGE
    return None


PHONE_PREFIX_TIMEZONE = {
    "+972": "Asia/Jerusalem",
    "+44": "Europe/London",
    "+33": "Europe/Paris",
    "+49": "Europe/Berlin",
    "+1": "America/New_York",
    "+61": "Australia/Sydney",
    "+91": "Asia/Kolkata",
}

def _infer_timezone(phone: str) -> str:
    for prefix, tz in PHONE_PREFIX_TIMEZONE.items():
        if phone.startswith(prefix):
            return tz
    return "UTC"


def _refresh_prompt(system_prompt: str, phone: str, lead_name: Optional[str] = None, lead_email: Optional[str] = None) -> str:
    now = datetime.now(ZoneInfo("UTC"))
    new_datetime = now.strftime("- Current date/time: **%A, %Y-%m-%d %H:%M UTC**")
    tz = _infer_timezone(phone)
    new_tz = f"- Customer timezone: **{tz}** (use this for all meeting scheduling - never ask the customer for their timezone)"

    updated = re.sub(r"- Current date/time: \*\*.*?\*\*", new_datetime, system_prompt)
    if "Customer timezone:" in updated:
        updated = re.sub(r"- Customer timezone: \*\*.*?\*\*.*", new_tz, updated)
    else:
        updated = updated.replace(new_datetime, new_datetime + "\n" + new_tz)

    # Inject lead block at the TOP (right after the first line) so GPT-4o sees it immediately.
    # Using UPPER CASE and explicit DO NOT ASK instruction for maximum salience.
    if lead_name or lead_email:
        parts = []
        if lead_name:
            parts.append(f"Name: {lead_name}")
        if lead_email:
            parts.append(f"Email: {lead_email}")
        lead_block = (
            "\n\n⚠️ LEAD INFO — ALREADY KNOWN — DO NOT ASK:\n"
            + "\n".join(f"  {p}" for p in parts)
            + "\nNever ask the lead for their name or email. Use the values above directly in conversation and for booking."
        )

        # Replace existing block if present; else insert right after the first line
        if "LEAD INFO — ALREADY KNOWN" in updated:
            updated = re.sub(r"\n\n⚠️ LEAD INFO.*?(?=\n\n|\Z)", lead_block, updated, flags=re.DOTALL)
        else:
            # Insert after the first newline (after "You are X. You are making an outbound sales call.")
            first_newline = updated.find("\n")
            if first_newline >= 0:
                updated = updated[:first_newline] + lead_block + updated[first_newline:]
            else:
                updated = lead_block + "\n" + updated

    return updated


async def _do_trigger(req: TriggerCallRequest, attempt: int = 1) -> dict:
    """Dial a call. The refreshed system prompt (current date, lead info) is sent as
    per-call assistantOverrides — no assistant PATCH, no propagation window, no sleep."""
    # Find session in memory first, fall back to DB
    matched_state = None
    for state in builder_service.sessions.values():
        if state.get("vapi_assistant_id") == req.assistant_id and state.get("config"):
            matched_state = state
            break
    if not matched_state:
        try:
            from database import load_all_agents
            for state in load_all_agents().values():
                if state.get("vapi_assistant_id") == req.assistant_id and state.get("config"):
                    matched_state = state
                    break
        except Exception:
            pass

    assistant_overrides = None
    if matched_state:
        config = dict(matched_state["config"])
        refreshed_prompt = _refresh_prompt(
            config["system_prompt"],
            req.phone_number,
            lead_name=req.lead_name,
            lead_email=req.lead_email,
        )
        assistant_overrides = vapi_service.build_prompt_overrides(refreshed_prompt)
        logger.warning(
            "trigger_call: session FOUND assistant_id=%s lead_provided=%s attempt=%d",
            req.assistant_id, bool(req.lead_name or req.lead_email), attempt,
        )
    else:
        known_ids = [s.get("vapi_assistant_id") for s in builder_service.sessions.values()]
        logger.warning(
            "trigger_call: NO session found for assistant_id=%s — ids in memory: %s",
            req.assistant_id, known_ids,
        )

    call_id, caller_number, pool_idx, pool_size = await vapi_service.trigger_call(
        req.phone_number,
        req.assistant_id,
        assistant_overrides=assistant_overrides,
    )
    _call_attempts[call_id] = {"req": req, "attempt": attempt}
    return {"call_id": call_id, "caller_number": caller_number, "pool_index": pool_idx, "pool_size": pool_size}


@router.post("/calls/trigger")
async def trigger_call(req: TriggerCallRequest) -> dict:
    try:
        return await _do_trigger(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _agent_name_from_assistant_id(assistant_id: str) -> str:
    """Look up agent name from in-memory sessions or DB, fallback to Vapi assistant store."""
    # Check live sessions first
    for state in builder_service.sessions.values():
        if state.get("vapi_assistant_id") == assistant_id:
            return state.get("agent_name") or "Ally"
    # Check DB
    try:
        from database import load_all_agents
        for state in load_all_agents().values():
            if state.get("vapi_assistant_id") == assistant_id:
                return state.get("agent_name") or "Ally"
    except Exception:
        pass
    return "Ally"


def _extract_call_fields(data: dict) -> dict:
    """Parse all useful fields out of a Vapi call object."""
    messages_list = data.get("messages") or []

    # Agent name: in messages[].assistantName, or look up from sessions by assistantId
    assistant_id = data.get("assistantId") or ""
    assistant_name = None
    for m in messages_list:
        if m.get("assistantName"):
            assistant_name = m["assistantName"]
            break
    if not assistant_name:
        assistant_name = _agent_name_from_assistant_id(assistant_id)

    # Transcript
    transcript = data.get("transcript") or ""

    # Cost
    cost = float(data.get("cost") or 0.0)

    # Phone
    phone = (data.get("customer") or {}).get("number", "")

    # Duration: durationSeconds is always null from Vapi REST API; use startedAt→endedAt
    # (actual talk time). startedAt is null when the carrier never connected the call —
    # duration is then genuinely 0. createdAt→updatedAt must NOT be used: it includes
    # dialing time and Vapi's record post-processing (a never-answered call showed 0:55).
    duration = int(data.get("durationSeconds") or 0)
    if not duration:
        try:
            started = data.get("startedAt", "")
            ended = data.get("endedAt", "")
            if started and ended:
                from datetime import datetime as _dt
                t1 = _dt.fromisoformat(started.replace("Z", "+00:00"))
                t2 = _dt.fromisoformat(ended.replace("Z", "+00:00"))
                duration = max(0, int((t2 - t1).total_seconds()))
        except Exception:
            pass

    # Latency: time from call start to first bot word (secondsFromStart on first bot message)
    latency_ms: Optional[float] = None
    bot_starts = [
        m.get("secondsFromStart")
        for m in messages_list
        if m.get("role") == "bot" and m.get("secondsFromStart") is not None
    ]
    if bot_starts:
        latency_ms = round(min(bot_starts) * 1000, 1)

    # Call date: use createdAt from Vapi, not "now"
    call_date = data.get("createdAt") or datetime.now(timezone.utc).isoformat()

    return {
        "assistant_name": assistant_name,
        "transcript": transcript,
        "cost": cost,
        "phone": phone,
        "duration": duration,
        "latency_ms": latency_ms,
        "call_date": call_date,
        "vapi_analysis": data.get("analysis") or {},
        "ended_reason": data.get("endedReason") or "",
    }


async def _build_log_from_fields(fields: dict, call_id: str) -> CallLog:
    transcript = fields["transcript"]
    vapi_analysis = fields["vapi_analysis"]
    ended_reason = fields.get("ended_reason") or ""
    failure_message = classify_failure(ended_reason, transcript)

    if failure_message:
        outcome = failure_message
        sentiment = "Neutral"
    elif isinstance(vapi_analysis, dict) and vapi_analysis.get("summary"):
        outcome = vapi_analysis["summary"]
        # Map successEvaluation → sentiment hint, then refine with Claude
        s = str(vapi_analysis.get("successEvaluation", "")).lower()
        sentiment = "Positive" if s in ("true", "yes") else ("Negative" if s in ("false", "no") else "Neutral")
    else:
        outcome = "Call completed"
        sentiment = "Neutral"

    if transcript and not failure_message:
        try:
            from routers.webhooks import _analyze_transcript, _booked_call_ids
            result = await _analyze_transcript(transcript)
            sentiment = result.sentiment
            if not (isinstance(vapi_analysis, dict) and vapi_analysis.get("summary")):
                outcome = result.outcome
        except Exception:
            pass

    from routers.webhooks import _booked_call_ids
    is_booked = call_id in _booked_call_ids
    _booked_call_ids.discard(call_id)

    return CallLog(
        id=str(uuid.uuid4()),
        agent_name=fields["assistant_name"],
        phone_number=fields["phone"],
        date=fields["call_date"],
        duration_seconds=fields["duration"],
        sentiment=sentiment,
        cost_usd=fields["cost"],
        outcome=outcome,
        transcript=transcript,
        latency_ms=fields["latency_ms"],
        vapi_call_id=call_id,
        is_booked=is_booked,
        ended_reason=ended_reason or None,
        is_failed=bool(failure_message),
    )


async def _create_log_from_vapi(call_id: str) -> None:
    """Fallback: fetch completed call from Vapi and save a log if one doesn't exist yet."""
    # Atomic check-and-mark: no await between checking and adding to the guard set,
    # so concurrent coroutines (webhook + SSE/syncCallLog) can't both slip through.
    if any(log.vapi_call_id == call_id for log in call_logs) or call_id in _creating_log_for:
        return
    _creating_log_for.add(call_id)
    try:
        data = await vapi_service.get_call(call_id)
        if not data.get("status") == "ended":
            return  # not finished yet
        # Re-check: webhook may have arrived while we were fetching
        if any(log.vapi_call_id == call_id for log in call_logs):
            return
        fields = _extract_call_fields(data)
        log = await _build_log_from_fields(fields, call_id)
        call_logs.append(log)
        try:
            from database import save_call_log
            save_call_log(log.model_dump())
        except Exception:
            pass
    except Exception:
        pass
    finally:
        _creating_log_for.discard(call_id)


async def sync_recent_calls() -> None:
    """Called on startup: pull last 20 Vapi calls and log any that are missing."""
    try:
        import httpx
        from config import settings
        headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
        async with httpx.AsyncClient() as c:
            resp = await c.get("https://api.vapi.ai/call?limit=20", headers=headers, timeout=15)
            if not resp.is_success:
                return
            calls = resp.json()
        known_ids = {log.vapi_call_id for log in call_logs}
        for call in calls:
            if call.get("status") != "ended":
                continue
            if call.get("type") != "outboundPhoneCall":
                continue  # inbound spam to the pool numbers is not our agents' work
            cid = call.get("id")
            if not cid or cid in known_ids:
                continue
            has_content = call.get("transcript") or (call.get("analysis") or {}).get("summary")
            is_failed = classify_failure(call.get("endedReason") or "", call.get("transcript") or "")
            if not has_content and not is_failed:
                continue  # skip empty non-failed calls (e.g. cancelled before ringing)
            fields = _extract_call_fields(call)
            log = await _build_log_from_fields(fields, cid)
            call_logs.append(log)
            known_ids.add(cid)
            try:
                from database import save_call_log
                save_call_log(log.model_dump())
            except Exception:
                pass
    except Exception:
        pass


@router.post("/calls/{call_id}/end")
async def end_call(call_id: str):
    """Hang up an active Vapi call and save the log."""
    try:
        await vapi_service.end_call(call_id)
    except Exception:
        pass  # best-effort — call may have already ended
    await asyncio.sleep(3)  # give Vapi time to finalize the call record
    await _create_log_from_vapi(call_id)
    return {"ok": True}


@router.get("/calls/status/{call_id}")
async def stream_call_status(call_id: str) -> StreamingResponse:
    async def generate():
        terminal = {"ended", "failed", "error"}
        current_id = call_id
        while True:
            ended_reason = ""
            try:
                status, ended_reason = await vapi_service.get_call_status(current_id)
            except Exception:
                status = "error"

            if status not in terminal:
                yield f"data: {json.dumps({'status': status, 'call_id': current_id})}\n\n"
                await asyncio.sleep(2)
                continue

            # Terminal: fetch the full call once for transcript-aware failure classification
            transcript = ""
            try:
                data = await vapi_service.get_call(current_id)
                ended_reason = data.get("endedReason") or ended_reason
                transcript = data.get("transcript") or ""
            except Exception:
                pass
            failure_message = classify_failure(ended_reason, transcript)

            # Carrier dropped the answer signal → the agent was never connected.
            # History shows an immediate redial almost always succeeds, so retry once.
            meta = _call_attempts.get(current_id)
            if (
                ended_reason == "customer-did-not-answer"
                and meta
                and meta["attempt"] < MAX_CALL_ATTEMPTS
            ):
                await _create_log_from_vapi(current_id)  # keep the failed attempt visible in logs
                try:
                    result = await _do_trigger(meta["req"], attempt=meta["attempt"] + 1)
                    current_id = result["call_id"]
                    yield f"data: {json.dumps({'status': 'retrying', 'call_id': current_id, 'ended_reason': ended_reason, 'failure_message': failure_message})}\n\n"
                    await asyncio.sleep(2)
                    continue
                except Exception:
                    pass  # redial failed — fall through and report the original failure

            yield f"data: {json.dumps({'status': status, 'call_id': current_id, 'ended_reason': ended_reason, 'failure_message': failure_message})}\n\n"
            # Wait a moment for the Vapi webhook to arrive, then fallback
            await asyncio.sleep(5)
            await _create_log_from_vapi(current_id)
            break

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/calls/sync/{call_id}")
async def sync_call_log(call_id: str) -> dict:
    """Frontend calls this after a call ends to ensure a log exists regardless of SSE/webhook reliability."""
    await _create_log_from_vapi(call_id)
    return {"synced": True}


@router.delete("/calls/logs/{log_id}")
async def delete_call_log(log_id: str) -> dict:
    global call_logs
    call_logs[:] = [l for l in call_logs if l.id != log_id]
    from database import delete_call_log as db_delete
    db_delete(log_id)
    return {"deleted": log_id}


@router.get("/calls/logs", response_model=list[CallLog])
async def get_call_logs() -> list[CallLog]:
    return list(reversed(call_logs))  # newest first
