from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from models import Agent, VapiAssistantConfig
import services.builder as builder_service
import services.vapi as vapi_service
from routers.calls import call_logs

router = APIRouter()


@router.get("/agents", response_model=list[Agent])
async def get_agents() -> list[Agent]:
    agents = []
    for session_id, state in builder_service.sessions.items():
        if not (state.get("vapi_assistant_id") and state.get("config")):
            continue

        config = VapiAssistantConfig(**state["config"])

        # Aggregate metrics from call_logs for this agent
        agent_logs = [l for l in call_logs if l.agent_name == config.name]
        last_call_at = agent_logs[-1].date if agent_logs else None
        avg_cost = round(sum(l.cost_usd for l in agent_logs) / len(agent_logs), 6) if agent_logs else None
        avg_latency = (
            round(sum(l.latency_ms for l in agent_logs if l.latency_ms is not None) /
                  max(1, sum(1 for l in agent_logs if l.latency_ms is not None)), 1)
            if any(l.latency_ms is not None for l in agent_logs)
            else None
        )
        sentiments = [l.sentiment for l in agent_logs]
        # Most common sentiment wins
        avg_sentiment = max(set(sentiments), key=sentiments.count) if sentiments else None

        # Query DB directly so retroactive patches and mid-session updates are reflected
        try:
            from database import engine
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT COUNT(*) FROM calllogrecord WHERE agent_name = :n AND is_booked = 1"),
                    {"n": config.name},
                ).fetchone()
                booked_count = row[0] if row else 0
        except Exception:
            booked_count = sum(1 for l in agent_logs if l.is_booked)
        attempted_logs = [l for l in agent_logs if not l.is_failed]
        success_rate = round(booked_count / len(attempted_logs) * 100, 1) if attempted_logs else None

        agents.append(
            Agent(
                id=session_id,
                name=config.name,
                status="active",
                config=config,
                vapi_assistant_id=state["vapi_assistant_id"],
                last_call_at=last_call_at,
                avg_cost_usd=avg_cost,
                avg_latency_ms=avg_latency,
                avg_sentiment=avg_sentiment,
                success_rate=success_rate,
                messages=state.get("messages", []),
            )
        )
    return agents


@router.delete("/agents/{session_id}")
async def delete_agent(session_id: str) -> dict:
    if session_id not in builder_service.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = builder_service.sessions.pop(session_id)

    # Delete from Vapi
    assistant_id = state.get("vapi_assistant_id")
    if assistant_id:
        try:
            await vapi_service.delete_assistant(assistant_id)
        except Exception:
            pass

    # Delete from DB
    try:
        from database import delete_agent as db_delete_agent
        db_delete_agent(session_id)
    except Exception:
        pass

    return {"deleted": session_id}


class PatchVoiceRequest(BaseModel):
    voice_id: str


@router.patch("/agents/{session_id}/voice")
async def patch_voice(session_id: str, req: PatchVoiceRequest) -> dict:
    if session_id not in builder_service.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = builder_service.sessions[session_id]
    if not state.get("config"):
        raise HTTPException(status_code=400, detail="Agent not built yet")

    state["voice_id"] = req.voice_id
    state["config"]["voice_id"] = req.voice_id

    config = VapiAssistantConfig(**state["config"])
    await vapi_service.create_or_update_assistant(config, state.get("vapi_assistant_id"))

    try:
        from database import save_agent
        save_agent(session_id, dict(state))
    except Exception:
        pass

    return {"voice_id": req.voice_id, "config": config.model_dump()}
