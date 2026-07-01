"""
Tests for the Vapi webhook handler.
Covers tool-call dispatch, end-of-call-report parsing, and error cases.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from routers.calls import call_logs
from models import CallLog


client = TestClient(app)


def post_webhook(body: dict) -> dict:
    resp = client.post("/api/webhooks/vapi", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# tool-calls dispatch - book_meeting
# ---------------------------------------------------------------------------

BOOK_MEETING_BODY = {
    "type": "tool-calls",
    "message": {
        "toolCallList": [
            {
                "id": "tc-001",
                "function": {
                    "name": "book_meeting",
                    "arguments": {
                        "attendee_name": "Oz Hayun",
                        "attendee_email": "oz@example.com",
                        "meeting_datetime_iso": "2026-07-01T14:00:00+03:00",
                        "timezone": "Asia/Jerusalem",
                    },
                },
            }
        ]
    },
}


def test_book_meeting_success():
    booking_resp = {"uid": "cal-booking-abc123", "id": 1}
    with patch("routers.webhooks.calcom_service.book_slot", AsyncMock(return_value=booking_resp)):
        result = post_webhook(BOOK_MEETING_BODY)

    assert "results" in result
    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r["toolCallId"] == "tc-001"
    assert "Meeting booked" in r["result"]
    assert "cal-booking-abc123" in r["result"]


def test_book_meeting_missing_email_fails_gracefully():
    body = {
        "type": "tool-calls",
        "message": {
            "toolCallList": [
                {
                    "id": "tc-002",
                    "function": {
                        "name": "book_meeting",
                        "arguments": {
                            "attendee_name": "Oz Hayun",
                            # attendee_email intentionally missing
                            "meeting_datetime_iso": "2026-07-01T14:00:00+03:00",
                            "timezone": "Asia/Jerusalem",
                        },
                    },
                }
            ]
        },
    }
    result = post_webhook(body)
    r = result["results"][0]
    assert "Booking failed" in r["result"]
    assert r["toolCallId"] == "tc-002"


def test_book_meeting_invalid_email_fails_gracefully():
    body = {
        "type": "tool-calls",
        "message": {
            "toolCallList": [
                {
                    "id": "tc-003",
                    "function": {
                        "name": "book_meeting",
                        "arguments": {
                            "attendee_name": "Oz",
                            "attendee_email": "not-an-email",
                            "meeting_datetime_iso": "2026-07-01T14:00:00+03:00",
                            "timezone": "Asia/Jerusalem",
                        },
                    },
                }
            ]
        },
    }
    result = post_webhook(body)
    r = result["results"][0]
    assert "Booking failed" in r["result"]


def test_book_meeting_calcom_error_returns_failure_message():
    with patch("routers.webhooks.calcom_service.book_slot", AsyncMock(side_effect=Exception("Cal.com 500"))):
        result = post_webhook(BOOK_MEETING_BODY)
    r = result["results"][0]
    assert "Booking failed" in r["result"]
    assert "Cal.com 500" in r["result"]


# ---------------------------------------------------------------------------
# tool-calls dispatch - qualify_lead
# ---------------------------------------------------------------------------

def test_qualify_lead_returns_recorded():
    body = {
        "type": "tool-calls",
        "message": {
            "toolCallList": [
                {
                    "id": "tc-q1",
                    "function": {
                        "name": "qualify_lead",
                        "arguments": {"result": "qualified", "reason": "Decision maker with budget"},
                    },
                }
            ]
        },
    }
    result = post_webhook(body)
    r = result["results"][0]
    assert r["toolCallId"] == "tc-q1"
    assert r["result"] == "Qualification recorded"


def test_unknown_tool_returns_error_message():
    body = {
        "type": "tool-calls",
        "message": {
            "toolCallList": [
                {
                    "id": "tc-unk",
                    "function": {"name": "do_magic", "arguments": {}},
                }
            ]
        },
    }
    result = post_webhook(body)
    r = result["results"][0]
    assert "Unknown tool" in r["result"]


def test_empty_tool_list_returns_empty_results():
    body = {"type": "tool-calls", "message": {"toolCallList": []}}
    result = post_webhook(body)
    assert result["results"] == []


# ---------------------------------------------------------------------------
# end-of-call-report
# ---------------------------------------------------------------------------

END_OF_CALL_BODY = {
    "type": "end-of-call-report",
    "message": {
        "call": {
            "assistant": {"name": "Alex"},
            "customer": {"number": "+972501234567"},
        },
        "transcript": "AI: Hi, this is Alex.\nUSER: Hi, not interested.\nAI: Thanks, have a good day.",
        "cost": 0.08,
        "durationSeconds": 45,
        "messages": [
            {"role": "bot", "secondsFromStart": 0.5, "message": "Hi"},
            {"role": "bot", "secondsFromStart": 2.1, "message": "Thanks"},
        ],
    },
}


def test_end_of_call_report_creates_log():
    initial_count = len(call_logs)
    sentiment_mock = MagicMock()
    sentiment_mock.sentiment = "Negative"
    sentiment_mock.outcome = "Lead not interested"

    with patch("routers.webhooks._analyze_transcript", AsyncMock(return_value=sentiment_mock)):
        result = post_webhook(END_OF_CALL_BODY)

    assert result == {"received": True}
    assert len(call_logs) == initial_count + 1

    log = call_logs[-1]
    assert log.agent_name == "Alex"
    assert log.phone_number == "+972501234567"
    assert log.duration_seconds == 45
    assert log.cost_usd == 0.08
    assert log.sentiment == "Negative"
    assert log.latency_ms == 500.0  # min(0.5, 2.1) * 1000


def test_end_of_call_report_extracts_min_latency():
    """latency_ms should be the MINIMUM bot response time (first response)."""
    body = {
        "type": "end-of-call-report",
        "message": {
            "call": {
                "assistant": {"name": "Bot"},
                "customer": {"number": "+441234567890"},
            },
            "transcript": "AI: Hello.\nUSER: Hi.",
            "cost": 0.01,
            "durationSeconds": 10,
            "messages": [
                {"role": "user", "secondsFromStart": 0.0, "message": "Hi"},
                {"role": "bot", "secondsFromStart": 1.2, "message": "Hello"},
                {"role": "bot", "secondsFromStart": 0.8, "message": "Hi there"},
            ],
        },
    }
    mock_sentiment = MagicMock(sentiment="Positive", outcome="Good call")
    with patch("routers.webhooks._analyze_transcript", AsyncMock(return_value=mock_sentiment)):
        post_webhook(body)

    log = call_logs[-1]
    assert log.latency_ms == 800.0  # min of 1.2 and 0.8 → 0.8 * 1000


def test_end_of_call_report_no_messages_latency_is_none():
    body = {
        "type": "end-of-call-report",
        "message": {
            "call": {"assistant": {"name": "Bot"}, "customer": {"number": "+1"}},
            "transcript": "",
            "cost": 0.0,
            "durationSeconds": 0,
            "messages": [],
        },
    }
    mock_sentiment = MagicMock(sentiment="Neutral", outcome="")
    with patch("routers.webhooks._analyze_transcript", AsyncMock(return_value=mock_sentiment)):
        post_webhook(body)

    log = call_logs[-1]
    assert log.latency_ms is None


def test_end_of_call_report_sentiment_failure_uses_neutral():
    """If sentiment analysis throws, fallback to Neutral - don't crash."""
    body = {
        "type": "end-of-call-report",
        "message": {
            "call": {"assistant": {"name": "Bot"}, "customer": {"number": "+972"}},
            "transcript": "some transcript",
            "cost": 0.05,
            "durationSeconds": 30,
            "messages": [],
        },
    }
    with patch("routers.webhooks._analyze_transcript", AsyncMock(side_effect=Exception("Anthropic down"))):
        result = post_webhook(body)

    assert result == {"received": True}
    log = call_logs[-1]
    assert log.sentiment == "Neutral"  # fallback


def test_end_of_call_missing_assistant_name_defaults_to_ally():
    body = {
        "type": "end-of-call-report",
        "message": {
            "call": {"assistant": "not-a-dict", "customer": {"number": "+972"}},
            "transcript": "",
            "cost": 0.0,
            "durationSeconds": 0,
            "messages": [],
        },
    }
    mock_sentiment = MagicMock(sentiment="Neutral", outcome="")
    with patch("routers.webhooks._analyze_transcript", AsyncMock(return_value=mock_sentiment)):
        post_webhook(body)

    log = call_logs[-1]
    assert log.agent_name == "Ally"


# ---------------------------------------------------------------------------
# Unknown event type - should not crash
# ---------------------------------------------------------------------------

def test_unknown_event_type_returns_received():
    body = {"type": "call-started", "message": {"callId": "xyz"}}
    result = post_webhook(body)
    assert result == {"received": True}


def test_empty_body_returns_received():
    result = post_webhook({})
    assert result == {"received": True}
