import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, agents, calls, webhooks
from config import settings

logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init DB schema
    from database import create_db, load_all_agents, load_all_call_logs
    create_db()

    # Hydrate in-memory state from DB so a restart doesn't lose agents/logs
    import services.builder as builder_service
    from routers.calls import call_logs
    from models import CallLog

    persisted_agents = load_all_agents()
    builder_service.sessions.update(persisted_agents)
    if persisted_agents:
        logger.info("Loaded %d agent(s) from DB", len(persisted_agents))

    persisted_logs = load_all_call_logs()
    call_logs.extend(CallLog(**l) for l in persisted_logs)
    if persisted_logs:
        logger.info("Loaded %d call log(s) from DB", len(persisted_logs))

    # Pull any calls from Vapi that we missed (backend restarts, webhook gaps)
    from routers.calls import sync_recent_calls
    await sync_recent_calls()

    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "VAPI_API_KEY": settings.vapi_api_key,
        "VAPI_INTL_PHONE_NUMBER_ID": settings.vapi_intl_phone_number_id,
        "CALCOM_API_KEY": settings.calcom_api_key,
        "CALCOM_EVENT_TYPE_ID": settings.calcom_event_type_id,
        "WEBHOOK_BASE_URL": settings.webhook_base_url,
    }.items() if not v]
    if missing:
        logger.warning("Missing env vars: %s", ", ".join(missing))
    yield


app = FastAPI(title="Ally API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(calls.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "ok", "service": "Ally API"}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "services": {
            "anthropic": bool(settings.anthropic_api_key),
            "vapi": bool(settings.vapi_api_key),
            "calcom": bool(settings.calcom_api_key),
            "webhook": bool(settings.webhook_base_url),
        },
    }
