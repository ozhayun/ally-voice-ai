import logging
from fastapi import APIRouter, HTTPException
from models import ChatRequest, ChatResponse, VapiAssistantConfig
import services.builder as builder_service

logger = logging.getLogger("chat")
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        state = await builder_service.run_builder(req.session_id, req.message)
    except Exception as e:
        logger.exception("Builder error for session %s", req.session_id)
        raise HTTPException(status_code=500, detail="Builder error — check server logs")

    config = None
    if state.get("config"):
        config = VapiAssistantConfig(**state["config"])

    return ChatResponse(
        reply=state["assistant_reply"],
        config=config,
        vapi_assistant_id=state.get("vapi_assistant_id"),
    )
