import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import instructor
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ValidationError

from config import settings
from models import BookMeetingToolPayload, CallLog
import services.calcom as calcom_service
from routers.calls import call_logs, _creating_log_for

logger = logging.getLogger("webhooks")
router = APIRouter()

# In-memory ring buffer of the last 20 webhook payloads for debugging
_webhook_log: list[dict] = []

# Call IDs where book_meeting succeeded — read by calls.py when building logs
_booked_call_ids: set[str] = set()

def _record_webhook(body: dict) -> None:
    _webhook_log.append({"ts": datetime.now(timezone.utc).isoformat(), "body": body})
    if len(_webhook_log) > 20:
        _webhook_log.pop(0)


@router.get("/webhooks/debug")
async def get_webhook_debug(secret: str = Query(default="")) -> dict:
    """Returns the last 20 raw payloads Vapi sent to this server.
    Protected by DEBUG_SECRET env var when set."""
    from fastapi import HTTPException
    if settings.debug_secret and secret != settings.debug_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"count": len(_webhook_log), "events": _webhook_log}


class SentimentResult(BaseModel):
    sentiment: str
    outcome: str


def _get_instructor_client():
    if not settings.anthropic_api_key:
        return None
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return instructor.from_anthropic(client)


async def _analyze_transcript(transcript: str) -> SentimentResult:
    client = _get_instructor_client()
    if client is None:
        return SentimentResult(sentiment="Neutral", outcome="Call completed (sentiment unavailable - no Anthropic key)")
    return await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system="Analyze this call transcript. Return sentiment as one of: Positive, Neutral, Negative. Return outcome as a one-sentence summary.",
        messages=[{"role": "user", "content": transcript}],
        response_model=SentimentResult,
    )


def _verify_vapi_signature(raw_body: bytes, signature_header: str) -> bool:
    """Return True if the HMAC-SHA256 signature matches, or if no secret is configured."""
    if not settings.vapi_webhook_secret:
        return True  # verification disabled — set VAPI_WEBHOOK_SECRET in .env to enable
    expected = hmac.new(
        settings.vapi_webhook_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/webhooks/vapi")
async def vapi_webhook(request: Request) -> dict:
    from fastapi import HTTPException
    raw_body = await request.body()
    sig = request.headers.get("x-vapi-signature", "")
    if not _verify_vapi_signature(raw_body, sig):
        logger.warning("Webhook signature verification failed — rejecting request")
        raise HTTPException(status_code=401, detail="Invalid signature")

    body = json.loads(raw_body)
    _record_webhook(body)
    message = body.get("message", body)
    # Vapi sends type at body.message.type, not body.type
    event_type = body.get("type", "") or (message.get("type", "") if isinstance(message, dict) else "")
    logger.info("vapi webhook: type=%r keys=%s", event_type, list(body.keys()))

    if event_type == "tool-calls" or "toolCallList" in message:
        tool_calls = message.get("toolCallList", [])
        call_id_for_tool = (message.get("call") or {}).get("id") or body.get("callId") or ""
        results = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {})

            if name == "book_meeting":
                try:
                    payload = BookMeetingToolPayload(**args)
                    booking = await calcom_service.book_slot(payload)
                    result = f"Meeting booked successfully for {payload.attendee_name} on {payload.meeting_datetime_iso}. Booking ID: {booking.get('uid', 'N/A')}"
                    if call_id_for_tool:
                        _booked_call_ids.add(call_id_for_tool)
                        # Mark booked in DB immediately — survives restarts
                        try:
                            from database import mark_call_booked
                            mark_call_booked(call_id_for_tool)
                        except Exception:
                            pass
                        # Also mark in-memory logs already created via SSE
                        for log in call_logs:
                            if log.vapi_call_id == call_id_for_tool:
                                log.is_booked = True
                except ValidationError as e:
                    result = f"Booking failed: missing required fields. {str(e)}"
                except Exception as e:
                    err = str(e)
                    if "slot not available" in err:
                        result = "slot not available - ask the lead to choose a different date or time"
                    else:
                        result = f"Booking failed: {err}"

            elif name == "qualify_lead":
                result = "Qualification recorded"

            else:
                result = f"Unknown tool: {name}"

            results.append({"toolCallId": tc.get("id"), "result": result})

        return {"results": results}

    if event_type == "end-of-call-report":
        call_obj = message.get("call", {}) if isinstance(message.get("call"), dict) else {}
        vapi_call_id = call_obj.get("id") or message.get("callId") or message.get("id")

        # ── Duplicate guard (must happen BEFORE any await) ──────────────────────
        # In asyncio, code between two awaits is atomic. We claim the call_id here,
        # before _analyze_transcript yields, so _create_log_from_vapi can't race us.
        if vapi_call_id:
            if vapi_call_id in _creating_log_for:
                logger.warning("end-of-call-report for %s: already being handled, dropping duplicate", vapi_call_id)
                return {"received": True}
            _creating_log_for.add(vapi_call_id)
        # ────────────────────────────────────────────────────────────────────────

        try:
            # assistant field is often "" in Vapi payloads — look up from our sessions by assistantId
            assistant_id = call_obj.get("assistantId") or message.get("assistantId") or ""
            if assistant_id:
                from routers.calls import _agent_name_from_assistant_id
                assistant_name = _agent_name_from_assistant_id(assistant_id)
            else:
                asst = call_obj.get("assistant") or message.get("assistant")
                assistant_name = asst.get("name", "Ally") if isinstance(asst, dict) else "Ally"

            transcript = message.get("transcript", "")
            cost = message.get("cost", 0.0) or 0.0
            duration = int(message.get("durationSeconds", 0) or 0)
            customer = call_obj.get("customer") or message.get("customer") or {}
            phone = customer.get("number", "") if isinstance(customer, dict) else ""

            # Extract latency: Vapi includes per-message latency in the messages array
            latency_ms: float | None = None
            messages_list = message.get("messages", [])
            latencies = [
                m.get("secondsFromStart")
                for m in messages_list
                if m.get("role") == "bot" and m.get("secondsFromStart") is not None
            ]
            if latencies:
                latency_ms = round(min(latencies) * 1000, 1)

            ended_reason = message.get("endedReason") or call_obj.get("endedReason") or ""
            from routers.calls import classify_failure
            failure_message = classify_failure(ended_reason, transcript)

            sentiment_result = SentimentResult(sentiment="Neutral", outcome=failure_message or "Call completed")
            if transcript and not failure_message:
                try:
                    sentiment_result = await _analyze_transcript(transcript)
                except Exception:
                    pass

            # If _create_log_from_vapi already created a log, enrich it
            existing = next((log for log in call_logs if log.vapi_call_id == vapi_call_id), None) if vapi_call_id else None
            if existing:
                existing.transcript = transcript or existing.transcript
                existing.cost_usd = float(cost) if cost else existing.cost_usd
                existing.duration_seconds = duration or existing.duration_seconds
                existing.sentiment = sentiment_result.sentiment
                existing.outcome = sentiment_result.outcome
                existing.latency_ms = latency_ms or existing.latency_ms
                existing.ended_reason = ended_reason or existing.ended_reason
                if vapi_call_id in _booked_call_ids:
                    existing.is_booked = True
                    _booked_call_ids.discard(vapi_call_id)
                try:
                    from database import save_call_log
                    save_call_log(existing.model_dump())
                except Exception:
                    pass
                return {"received": True}

            is_booked = bool(vapi_call_id and vapi_call_id in _booked_call_ids)
            if is_booked:
                _booked_call_ids.discard(vapi_call_id)
            log = CallLog(
                id=str(uuid.uuid4()),
                agent_name=assistant_name,
                phone_number=phone,
                date=datetime.now(timezone.utc).isoformat(),
                duration_seconds=duration,
                sentiment=sentiment_result.sentiment,
                cost_usd=float(cost),
                outcome=sentiment_result.outcome,
                transcript=transcript,
                latency_ms=latency_ms,
                vapi_call_id=vapi_call_id,
                is_booked=is_booked,
                ended_reason=ended_reason or None,
            )
            call_logs.append(log)
            try:
                from database import save_call_log
                save_call_log(log.model_dump())
            except Exception:
                pass
        finally:
            if vapi_call_id:
                _creating_log_for.discard(vapi_call_id)

        return {"received": True}

    return {"received": True}
