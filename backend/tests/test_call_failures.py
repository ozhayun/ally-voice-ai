"""
Tests for silent-call failure handling (branch fix/silent-call-failures):
- classify_failure: endedReason → human-readable failure message
- _do_trigger: refreshed prompt travels as per-call assistantOverrides, never a PATCH
- stream_call_status: auto-redials exactly once on customer-did-not-answer
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

import services.vapi as vapi_service
from models import TriggerCallRequest
from routers.calls import (
    DEAD_AIR_MESSAGE,
    HARD_FAILURE_REASONS,
    _call_attempts,
    _do_trigger,
    classify_failure,
    stream_call_status,
)
import services.builder as builder_service


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------

def test_customer_did_not_answer_is_failure():
    msg = classify_failure("customer-did-not-answer", "")
    assert msg == HARD_FAILURE_REASONS["customer-did-not-answer"]


def test_customer_busy_is_failure():
    assert classify_failure("customer-busy", "") is not None


def test_call_start_error_is_failure():
    msg = classify_failure("call.start.error-vapi-number-international", "")
    assert msg is not None and "call.start.error-vapi-number-international" in msg


def test_silence_timeout_without_user_turns_is_dead_air():
    # Real case: call 019f139c-d4df — greeting cut off, caller never transcribed
    transcript = "AI: Hey. I need an\nAI: Separately,\n"
    assert classify_failure("silence-timed-out", transcript) == DEAD_AIR_MESSAGE


def test_silence_timeout_with_conversation_is_not_failure():
    # Real case: call 019f13de-a396 — 110s of dialogue, then silence ended it
    transcript = "AI: Hey. I'm Dan from Aussie surf.\nUser: I made a video.\nAI: That's awesome.\n"
    assert classify_failure("silence-timed-out", transcript) is None


def test_normal_end_reasons_are_not_failures():
    assert classify_failure("assistant-said-end-call-phrase", "AI: bye\n") is None
    assert classify_failure("customer-ended-call", "") is None
    assert classify_failure("", "") is None


# ---------------------------------------------------------------------------
# _do_trigger — assistantOverrides instead of PATCH
# ---------------------------------------------------------------------------

def _session_with_assistant(assistant_id: str) -> dict:
    return {
        "vapi_assistant_id": assistant_id,
        "agent_name": "Dan",
        "config": {
            "name": "Dan",
            "first_message": "Hey! I'm Dan from Aussie Surf.",
            "system_prompt": "You are Dan.\n- Current date/time: **Monday, 2026-06-29 04:14 UTC**",
            "voice_id": "Skylar",
            "qualification_criteria": {"questions": [], "disqualification_signals": []},
            "max_call_duration_seconds": 300,
        },
    }


async def test_trigger_sends_prompt_as_overrides_and_never_patches():
    builder_service.sessions["s1"] = _session_with_assistant("asst-1")
    req = TriggerCallRequest(
        phone_number="+972508440195",
        assistant_id="asst-1",
        lead_name="Oz",
        lead_email="oz@example.com",
    )
    with (
        patch.object(vapi_service, "trigger_call", new=AsyncMock(return_value=("call-1", "+1555", 1, 1))) as mock_dial,
        patch.object(vapi_service, "create_or_update_assistant", new=AsyncMock()) as mock_patch,
    ):
        result = await _do_trigger(req)

    mock_patch.assert_not_called()  # the old PATCH+sleep(2) race is gone
    mock_dial.assert_awaited_once()
    overrides = mock_dial.await_args.kwargs["assistant_overrides"]
    prompt = overrides["model"]["messages"][0]["content"]
    assert "LEAD INFO" in prompt and "Oz" in prompt
    assert "Asia/Jerusalem" in prompt  # timezone inferred from +972
    assert result["call_id"] == "call-1"
    assert _call_attempts["call-1"]["attempt"] == 1


async def test_trigger_without_session_dials_with_no_overrides():
    req = TriggerCallRequest(phone_number="+12125551234", assistant_id="unknown")
    with patch.object(
        vapi_service, "trigger_call", new=AsyncMock(return_value=("call-2", "", 1, 1))
    ) as mock_dial:
        await _do_trigger(req)
    assert mock_dial.await_args.kwargs["assistant_overrides"] is None


# ---------------------------------------------------------------------------
# stream_call_status — auto-redial exactly once on customer-did-not-answer
# ---------------------------------------------------------------------------

def _fake_call(call_id: str, ended_reason: str) -> dict:
    return {
        "id": call_id,
        "status": "ended",
        "endedReason": ended_reason,
        "transcript": "",
        "messages": [],
        "customer": {"number": "+972508440195"},
        "createdAt": "2026-07-06T10:00:00.000Z",
        "updatedAt": "2026-07-06T10:00:55.000Z",
    }


async def _collect_sse_events(call_id: str) -> list[dict]:
    response = await stream_call_status(call_id)
    events = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


async def test_no_answer_triggers_exactly_one_redial():
    _call_attempts["call-A"] = {
        "req": TriggerCallRequest(phone_number="+972508440195", assistant_id="asst-1"),
        "attempt": 1,
    }
    reasons = {"call-A": "customer-did-not-answer", "call-B": "customer-ended-call"}

    async def fake_status(cid):
        return "ended", reasons[cid]

    async def fake_get_call(cid):
        return _fake_call(cid, reasons[cid])

    with (
        patch.object(vapi_service, "get_call_status", new=fake_status),
        patch.object(vapi_service, "get_call", new=fake_get_call),
        patch.object(vapi_service, "trigger_call", new=AsyncMock(return_value=("call-B", "", 1, 1))) as mock_dial,
        patch("routers.calls.asyncio.sleep", new=AsyncMock()),
        patch("database.save_call_log"),
    ):
        events = await _collect_sse_events("call-A")

    mock_dial.assert_awaited_once()
    retrying = [e for e in events if e["status"] == "retrying"]
    assert len(retrying) == 1
    assert retrying[0]["call_id"] == "call-B"
    assert retrying[0]["ended_reason"] == "customer-did-not-answer"
    final = events[-1]
    assert final["status"] == "ended"
    assert final["call_id"] == "call-B"
    assert final["failure_message"] is None  # second attempt was a normal call


async def test_no_answer_twice_does_not_redial_again():
    _call_attempts["call-A"] = {
        "req": TriggerCallRequest(phone_number="+972508440195", assistant_id="asst-1"),
        "attempt": 1,
    }

    async def fake_status(cid):
        return "ended", "customer-did-not-answer"

    async def fake_get_call(cid):
        return _fake_call(cid, "customer-did-not-answer")

    with (
        patch.object(vapi_service, "get_call_status", new=fake_status),
        patch.object(vapi_service, "get_call", new=fake_get_call),
        patch.object(vapi_service, "trigger_call", new=AsyncMock(return_value=("call-B", "", 1, 1))) as mock_dial,
        patch("routers.calls.asyncio.sleep", new=AsyncMock()),
        patch("database.save_call_log"),
    ):
        events = await _collect_sse_events("call-A")

    mock_dial.assert_awaited_once()  # call-B fails the same way but is NOT retried
    final = events[-1]
    assert final["status"] == "ended"
    assert final["ended_reason"] == "customer-did-not-answer"
    assert final["failure_message"]  # surfaced to the UI


@pytest.fixture(autouse=True)
def clear_call_attempts():
    _call_attempts.clear()
    yield
    _call_attempts.clear()
