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


@router.post("/calls/trigger")
async def trigger_call(req: TriggerCallRequest) -> dict:
    try:
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

        if matched_state:
            config = dict(matched_state["config"])
            refreshed_prompt = _refresh_prompt(
                config["system_prompt"],
                req.phone_number,
                lead_name=req.lead_name,
                lead_email=req.lead_email,
            )
            config["system_prompt"] = refreshed_prompt
            logger.warning(
                "trigger_call: session FOUND assistant_id=%s lead_provided=%s",
                req.assistant_id, bool(req.lead_name or req.lead_email),
            )
            try:
                from models import VapiAssistantConfig
                await vapi_service.create_or_update_assistant(VapiAssistantConfig(**config), req.assistant_id)
                logger.warning("trigger_call: PATCH ok")
            except Exception as patch_err:
                logger.warning("trigger_call: PATCH failed (%s)", patch_err)
            await asyncio.sleep(2)  # give Vapi time to propagate the assistant update before dialing
        else:
            known_ids = [s.get("vapi_assistant_id") for s in builder_service.sessions.values()]
            logger.warning(
                "trigger_call: NO session found for assistant_id=%s — ids in memory: %s",
                req.assistant_id, known_ids,
            )

        call_id, caller_number, pool_idx, pool_size = await vapi_service.trigger_call(
            req.phone_number,
            req.assistant_id,
        )
        return {"call_id": call_id, "caller_number": caller_number, "pool_index": pool_idx, "pool_size": pool_size}
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

    # Duration: durationSeconds is always null from Vapi REST API; calculate from timestamps
    duration = int(data.get("durationSeconds") or 0)
    if not duration:
        try:
            created = data.get("createdAt", "")
            updated = data.get("updatedAt", "")
            if created and updated:
                from datetime import datetime as _dt
                t1 = _dt.fromisoformat(created.replace("Z", "+00:00"))
                t2 = _dt.fromisoformat(updated.replace("Z", "+00:00"))
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
    }


async def _build_log_from_fields(fields: dict, call_id: str) -> CallLog:
    transcript = fields["transcript"]
    vapi_analysis = fields["vapi_analysis"]

    if isinstance(vapi_analysis, dict) and vapi_analysis.get("summary"):
        outcome = vapi_analysis["summary"]
        # Map successEvaluation → sentiment hint, then refine with Claude
        s = str(vapi_analysis.get("successEvaluation", "")).lower()
        sentiment = "Positive" if s in ("true", "yes") else ("Negative" if s in ("false", "no") else "Neutral")
    else:
        outcome = "Call completed"
        sentiment = "Neutral"

    if transcript:
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
            cid = call.get("id")
            if not cid or cid in known_ids:
                continue
            if not call.get("transcript") and not (call.get("analysis") or {}).get("summary"):
                continue  # skip empty/failed calls
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
        while True:
            try:
                status = await vapi_service.get_call_status(call_id)
            except Exception:
                status = "error"
            yield f"data: {json.dumps({'status': status})}\n\n"
            if status in terminal:
                # Wait a moment for the Vapi webhook to arrive, then fallback
                await asyncio.sleep(5)
                await _create_log_from_vapi(call_id)
                break
            await asyncio.sleep(2)

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
