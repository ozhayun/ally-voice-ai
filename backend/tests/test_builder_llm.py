"""
Tests for LLM-dependent builder nodes with mocked instructor.
Tests the state machine wiring - not the LLM output quality.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.builder import (
    gather_requirements,
    compile_config,
    run_builder,
    _make_initial_state,
    RequirementsExtract,
    sessions,
)
from models import VapiAssistantConfig, QualificationCriteria


# ---------------------------------------------------------------------------
# gather_requirements - mock instructor, verify state updates
# ---------------------------------------------------------------------------

FULL_EXTRACT = RequirementsExtract(
    goal="Book product demos with SaaS founders",
    target_audience="B2B SaaS founders in Series A",
    qualifying_questions=[
        "Are you the primary decision maker?",
        "What CRM are you currently using?",
        "Do you have a sales team?",
    ],
    agent_name="Alex",
    company_name="Acme Corp",
    follow_up_question="",
)

PARTIAL_EXTRACT = RequirementsExtract(
    goal="Book demos",
    target_audience=None,
    qualifying_questions=None,
    agent_name=None,
    follow_up_question="Who is your target audience?",
)


@pytest.mark.asyncio
async def test_gather_requirements_partial_sets_needs_more_info():
    state = _make_initial_state()
    state["messages"] = [{"role": "user", "content": "I want an agent to book demos."}]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=PARTIAL_EXTRACT)

    with patch("services.builder._instructor_client", mock_client):
        result = await gather_requirements(state)

    assert result["needs_more_info"] is True
    assert result["goal"] == "Book demos"
    assert result["target_audience"] is None
    assert "?" in result["assistant_reply"]


@pytest.mark.asyncio
async def test_gather_requirements_full_clears_needs_more_info():
    state = _make_initial_state()
    state["messages"] = [{"role": "user", "content": "Full brief here."}]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=FULL_EXTRACT)

    with patch("services.builder._instructor_client", mock_client):
        result = await gather_requirements(state)

    assert result["needs_more_info"] is False
    assert result["goal"] == FULL_EXTRACT.goal
    assert result["target_audience"] == FULL_EXTRACT.target_audience
    assert result["agent_name"] == "Alex"


@pytest.mark.asyncio
async def test_gather_requirements_preserves_prior_state():
    """If goal was already set in state, partial extract should keep it."""
    state = _make_initial_state()
    state["goal"] = "Already set goal"
    state["messages"] = [{"role": "user", "content": "My target is B2B SaaS."}]

    extract = RequirementsExtract(
        goal=None,  # LLM didn't re-extract it
        target_audience="B2B SaaS",
        qualifying_questions=None,
        agent_name=None,
        follow_up_question="What qualifying questions should I ask?",
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=extract)

    with patch("services.builder._instructor_client", mock_client):
        result = await gather_requirements(state)

    # Should carry forward the existing goal
    assert result["goal"] == "Already set goal"
    assert result["target_audience"] == "B2B SaaS"


# ---------------------------------------------------------------------------
# compile_config - mock instructor, verify config schema
# ---------------------------------------------------------------------------

VALID_CONFIG = VapiAssistantConfig(
    name="Alex",
    first_message="Hi, this is Alex calling from Acme. Is now a good time?",
    system_prompt=(
        "You are Alex, a sales agent.\n"
        "- Current date/time: **2026-06-29 10:00 UTC**\n"
        "- Customer timezone: **Asia/Jerusalem** (use this - never ask)\n"
        "Goal: book demos with SaaS founders."
    ),
    voice_id="alloy",
    qualification_criteria=QualificationCriteria(
        questions=["Are you the decision maker?"],
        disqualification_signals=["not interested", "wrong number"],
    ),
    max_call_duration_seconds=300,
)


@pytest.mark.asyncio
async def test_compile_config_returns_config_dict():
    state = _make_initial_state()
    state["goal"] = "Book demos"
    state["target_audience"] = "B2B SaaS founders"
    state["qualifying_questions"] = ["Are you the decision maker?"]
    state["agent_name"] = "Alex"

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=VALID_CONFIG)

    with patch("services.builder._instructor_client", mock_client):
        result = await compile_config(state)

    assert "config" in result
    assert result["config"]["name"] == "Alex"
    assert result["config"]["voice_id"] == "Skylar"
    assert "assistant_reply" in result


@pytest.mark.asyncio
async def test_compile_config_uses_agent_name_fallback():
    """If agent_name is missing from state, should default to 'Ally'."""
    state = _make_initial_state()
    state["goal"] = "Book demos"
    state["target_audience"] = "Founders"
    state["qualifying_questions"] = ["Q1?"]
    state["agent_name"] = None  # Missing

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=VALID_CONFIG)

    with patch("services.builder._instructor_client", mock_client):
        # Should not raise
        result = await compile_config(state)
    assert result["config"] is not None


# ---------------------------------------------------------------------------
# run_builder - integration test mocking both instructor and vapi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_builder_new_session_returns_reply():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=PARTIAL_EXTRACT)

    with patch("services.builder._instructor_client", mock_client):
        result = await run_builder("test-session-001", "I want to book demos")

    assert result["assistant_reply"] != ""
    assert "test-session-001" in sessions
    # Message appended to history
    msgs = sessions["test-session-001"]["messages"]
    assert any(m["role"] == "user" for m in msgs)
    assert any(m["role"] == "assistant" for m in msgs)


@pytest.mark.asyncio
async def test_run_builder_multi_turn_accumulates_state():
    """Second message should carry forward state from the first."""
    sid = "test-session-multi"

    mock_client = MagicMock()
    # Turn 1: goal extracted
    turn1 = RequirementsExtract(
        goal="Book demos", target_audience=None,
        qualifying_questions=None, agent_name=None,
        follow_up_question="Who is your audience?",
    )
    # Turn 2: audience added
    turn2 = RequirementsExtract(
        goal=None, target_audience="SaaS founders",
        qualifying_questions=None, agent_name=None,
        follow_up_question="What questions should I ask?",
    )
    mock_client.messages.create = AsyncMock(side_effect=[turn1, turn2])

    with patch("services.builder._instructor_client", mock_client):
        await run_builder(sid, "I want to book demos")
        await run_builder(sid, "My audience is SaaS founders")

    final = sessions[sid]
    assert final["goal"] == "Book demos"
    assert final["target_audience"] == "SaaS founders"


@pytest.mark.asyncio
async def test_run_builder_full_info_calls_vapi():
    """When all info is present, the graph should call compile_config and sync_to_vapi."""
    sid = "test-session-full"

    mock_instructor = MagicMock()
    mock_instructor.messages.create = AsyncMock(side_effect=[FULL_EXTRACT, VALID_CONFIG])

    with (
        patch("services.builder._instructor_client", mock_instructor),
        patch("services.vapi.create_or_update_assistant", AsyncMock(return_value="vapi-id-abc123")),
    ):
        result = await run_builder(sid, "Here is all the info.")

    assert result["vapi_assistant_id"] == "vapi-id-abc123"
    assert result["config"] is not None
    assert result["needs_more_info"] is False


@pytest.mark.asyncio
async def test_run_builder_isolates_sessions():
    """Two different session IDs should not share state."""
    mock_client = MagicMock()
    extract_a = RequirementsExtract(
        goal="Goal A", target_audience=None,
        qualifying_questions=None, agent_name=None,
        follow_up_question="Who?",
    )
    extract_b = RequirementsExtract(
        goal="Goal B", target_audience=None,
        qualifying_questions=None, agent_name=None,
        follow_up_question="Who?",
    )
    mock_client.messages.create = AsyncMock(side_effect=[extract_a, extract_b])

    with patch("services.builder._instructor_client", mock_client):
        await run_builder("session-A", "I want Goal A")
        await run_builder("session-B", "I want Goal B")

    assert sessions["session-A"]["goal"] == "Goal A"
    assert sessions["session-B"]["goal"] == "Goal B"
