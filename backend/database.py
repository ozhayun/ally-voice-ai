import json
from pathlib import Path
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select

DB_PATH = Path(__file__).parent / "ally.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class AgentRecord(SQLModel, table=True):
    session_id: str = Field(primary_key=True)
    state_json: str  # full BuilderState serialized as JSON
    updated_at: str


class CallLogRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_name: str
    phone_number: str
    date: str
    duration_seconds: int
    sentiment: str
    cost_usd: float
    outcome: str
    transcript: str
    latency_ms: Optional[float] = None
    vapi_call_id: Optional[str] = None
    is_booked: bool = False
    ended_reason: Optional[str] = None
    is_failed: bool = False


def create_db() -> None:
    SQLModel.metadata.create_all(engine)
    # Migrate existing DBs that predate later columns
    from sqlalchemy import text
    for ddl in (
        "ALTER TABLE calllogrecord ADD COLUMN is_booked INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE calllogrecord ADD COLUMN ended_reason VARCHAR",
        "ALTER TABLE calllogrecord ADD COLUMN is_failed INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            with engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
        except Exception:
            pass  # column already exists
    # Backfill rows written before is_failed existed. Never-connected calls also carry a
    # bogus duration (old code measured createdAt→updatedAt, which spans dialing +
    # Vapi post-processing) — zero it, since the agent never spoke.
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE calllogrecord SET is_failed = 1 WHERE outcome LIKE 'Failed —%'"))
            conn.execute(text(
                "UPDATE calllogrecord SET duration_seconds = 0 WHERE is_failed = 1 AND ended_reason IN "
                "('customer-did-not-answer', 'customer-busy', 'twilio-failed-to-connect-call')"
            ))
            conn.commit()
    except Exception:
        pass


# --- Agent (session) persistence ---

def save_agent(session_id: str, state: dict) -> None:
    from datetime import datetime, timezone
    with Session(engine) as db:
        record = db.get(AgentRecord, session_id)
        if record:
            record.state_json = json.dumps(state)
            record.updated_at = datetime.now(timezone.utc).isoformat()
        else:
            record = AgentRecord(
                session_id=session_id,
                state_json=json.dumps(state),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        db.add(record)
        db.commit()


def delete_agent(session_id: str) -> None:
    with Session(engine) as db:
        record = db.get(AgentRecord, session_id)
        if record:
            db.delete(record)
            db.commit()


def load_all_agents() -> dict[str, dict]:
    with Session(engine) as db:
        records = db.exec(select(AgentRecord)).all()
        return {r.session_id: json.loads(r.state_json) for r in records}


# --- Call log persistence ---

def save_call_log(log: dict) -> None:
    with Session(engine) as db:
        record = CallLogRecord(**log)
        db.merge(record)  # upsert — handles duplicate saves from webhook + SSE
        db.commit()


def load_all_call_logs() -> list[dict]:
    with Session(engine) as db:
        records = db.exec(select(CallLogRecord)).all()
        return [r.model_dump() for r in records]


def delete_call_log(log_id: str) -> None:
    with Session(engine) as db:
        record = db.get(CallLogRecord, log_id)
        if record:
            db.delete(record)
            db.commit()


def rename_agent_in_logs(old_name: str, new_name: str) -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE calllogrecord SET agent_name = :new WHERE agent_name = :old"),
            {"new": new_name, "old": old_name},
        )
        conn.commit()


def mark_call_booked(vapi_call_id: str) -> None:
    """Flip is_booked=True for the given vapi_call_id immediately when booking succeeds."""
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE calllogrecord SET is_booked = 1 WHERE vapi_call_id = :cid"),
            {"cid": vapi_call_id},
        )
        conn.commit()
