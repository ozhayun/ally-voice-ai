"""
Tests for pure/deterministic builder logic - no LLM calls needed.
These run instantly and never hit external APIs.
"""
import pytest
from services.builder import _route_after_gather, _make_initial_state, RequirementsExtract
from routers.calls import _infer_timezone, _refresh_prompt


# ---------------------------------------------------------------------------
# _route_after_gather - routing node, pure function
# ---------------------------------------------------------------------------

def _state(needs_more_info: bool):
    s = _make_initial_state()
    s["needs_more_info"] = needs_more_info
    return s


def test_route_needs_more_info_goes_to_end():
    from langgraph.graph import END
    assert _route_after_gather(_state(True)) == END


def test_route_all_info_goes_to_compile():
    assert _route_after_gather(_state(False)) == "compile_config"


# ---------------------------------------------------------------------------
# _make_initial_state - verify defaults
# ---------------------------------------------------------------------------

def test_initial_state_defaults():
    s = _make_initial_state()
    assert s["needs_more_info"] is True
    assert s["goal"] is None
    assert s["agent_name"] is None
    assert s["vapi_assistant_id"] is None
    assert s["messages"] == []
    assert isinstance(s["assistant_reply"], str)
    assert len(s["assistant_reply"]) > 0


# ---------------------------------------------------------------------------
# _infer_timezone - prefix-based lookup
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phone,expected", [
    ("+972501234567", "Asia/Jerusalem"),
    ("+441234567890", "Europe/London"),
    ("+33123456789", "Europe/Paris"),
    ("+491234567890", "Europe/Berlin"),
    ("+12125551234", "America/New_York"),
    ("+61412345678", "Australia/Sydney"),
    ("+911234567890", "Asia/Kolkata"),
    ("+886123456789", "UTC"),       # unknown prefix → UTC
    ("05001234567", "UTC"),          # no leading +
    ("", "UTC"),
])
def test_infer_timezone(phone, expected):
    assert _infer_timezone(phone) == expected


# ---------------------------------------------------------------------------
# _refresh_prompt - datetime injection
# ---------------------------------------------------------------------------

SAMPLE_PROMPT = (
    "You are a sales agent.\n"
    "- Current date/time: **2026-01-01 00:00 UTC**\n"
    "- Customer timezone: **UTC** (use this for all meeting scheduling - never ask the customer for their timezone)\n"
    "Ask qualifying questions."
)

def test_refresh_prompt_updates_datetime():
    result = _refresh_prompt(SAMPLE_PROMPT, "+972501234567")
    assert "2026-01-01 00:00 UTC" not in result
    assert "Current date/time:" in result


def test_refresh_prompt_updates_timezone_israel():
    result = _refresh_prompt(SAMPLE_PROMPT, "+972501234567")
    assert "Asia/Jerusalem" in result


def test_refresh_prompt_updates_timezone_uk():
    result = _refresh_prompt(SAMPLE_PROMPT, "+441234567890")
    assert "Europe/London" in result


def test_refresh_prompt_no_datetime_line_appends():
    """If the prompt has no existing date/time line, it should still work without crashing."""
    bare = "You are a sales agent."
    result = _refresh_prompt(bare, "+972501234567")
    # Should not raise, may or may not inject - just confirm no crash
    assert isinstance(result, str)


def test_refresh_prompt_never_asks_timezone():
    """The injected timezone line must include the instruction not to ask."""
    result = _refresh_prompt(SAMPLE_PROMPT, "+972501234567")
    assert "never ask the customer" in result


# ---------------------------------------------------------------------------
# RequirementsExtract - schema validation
# ---------------------------------------------------------------------------

def test_requirements_extract_all_optional():
    r = RequirementsExtract(follow_up_question="What is your goal?")
    assert r.goal is None
    assert r.target_audience is None
    assert r.qualifying_questions is None
    assert r.agent_name is None


def test_requirements_extract_full():
    r = RequirementsExtract(
        goal="Book SaaS demos",
        target_audience="B2B SaaS founders",
        qualifying_questions=["Are you the decision maker?", "What CRM do you use?"],
        agent_name="Alex",
        follow_up_question="",
    )
    assert r.goal == "Book SaaS demos"
    assert len(r.qualifying_questions) == 2
    assert r.agent_name == "Alex"


def test_requirements_extract_requires_follow_up():
    with pytest.raises(Exception):
        RequirementsExtract()  # follow_up_question is required
