import logging
import httpx
from models import VapiAssistantConfig, BookMeetingToolPayload
from config import settings

logger = logging.getLogger("vapi")

_call_counter = 0


def _get_pool() -> list[tuple[str, str]]:
    """Returns list of (phone_number_id, display_number) pairs from the pool config."""
    ids = [x.strip() for x in settings.vapi_phone_number_ids.split(",") if x.strip()]
    numbers = [x.strip() for x in settings.vapi_phone_numbers.split(",") if x.strip()]
    if ids:
        return [(ids[i], numbers[i] if i < len(numbers) else "") for i in range(len(ids))]
    if settings.vapi_phone_number_id:
        return [(settings.vapi_phone_number_id, "")]
    return []


def _pick_from_pool(destination: str = "") -> tuple[str, str, int, int]:
    """Round-robin selection. Falls back to Twilio for international numbers.
    Returns (phone_number_id, display_number, 1-based index, pool size)."""
    global _call_counter
    # International call (non-US) → use Twilio fallback number
    is_international = destination and not destination.startswith("+1")
    if is_international and settings.vapi_intl_phone_number_id:
        return settings.vapi_intl_phone_number_id, "", 0, 0
    pool = _get_pool()
    if not pool:
        raise ValueError("No phone numbers configured. Set VAPI_PHONE_NUMBER_IDS in .env")
    idx = _call_counter % len(pool)
    _call_counter += 1
    phone_id, phone_str = pool[idx]
    return phone_id, phone_str, idx + 1, len(pool)


CARTESIA_VOICES = {
    "Skylar":   "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",  # female, friendly American
    "Corey":    "630ed21c-2c5c-41cf-9d82-10a7fd668370",  # male, supportive American
    "Gemma":    "62ae83ad-4f6a-430b-af41-a9bede9286ca",  # female, British
    "Cora":     "c46cf1f6-49a1-4d67-9a57-ff859a4046d3",  # female, British
    "Archie":   "ef191366-f52f-447a-a398-ed8c0f2943a1",  # male, British
    "Daniel":   "47c38ca4-5f35-497b-b1a3-415245fb35e1",  # male, American
}
CARTESIA_DEFAULT_NAME = "Skylar"

def _build_voice_block(voice_id: str) -> dict:
    # voice_id is either a Cartesia UUID directly or a display name
    if voice_id in CARTESIA_VOICES.values():
        return {"provider": "cartesia", "voiceId": voice_id}
    resolved = CARTESIA_VOICES.get(voice_id, CARTESIA_VOICES[CARTESIA_DEFAULT_NAME])
    return {"provider": "cartesia", "voiceId": resolved}


def _build_tools() -> list[dict]:
    webhook_url = f"{settings.webhook_base_url}/api/webhooks/vapi"
    return [
        {
            "type": "function",
            "function": {
                "name": "qualify_lead",
                "description": "Record whether the lead is qualified or disqualified based on the conversation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string",
                            "enum": ["qualified", "disqualified"],
                            "description": "Qualification outcome",
                        },
                        "reason": {"type": "string", "description": "Brief reason for the outcome"},
                    },
                    "required": ["result", "reason"],
                },
            },
            "server": {"url": webhook_url},
        },
        {
            "type": "function",
            "function": {
                "name": "book_meeting",
                "description": "Book a calendar meeting with the lead. Collect all required info before calling.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "attendee_name": {"type": "string"},
                        "attendee_email": {"type": "string", "format": "email"},
                        "meeting_datetime_iso": {
                            "type": "string",
                            "description": "ISO 8601 with timezone offset, e.g. 2026-07-01T14:00:00-05:00",
                        },
                        "timezone": {"type": "string"},
                        "title": {
                            "type": "string",
                            "description": "Short meeting title, e.g. 'Intro Call - Oz & Anne from Deep Blue Freediving'. Include the attendee name and your company name.",
                        },
                    },
                    "required": ["attendee_name", "attendee_email", "meeting_datetime_iso", "timezone"],
                },
            },
            "server": {"url": webhook_url},
        },
    ]


def _build_model_block(system_prompt: str) -> dict:
    return {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.3,
        "messages": [{"role": "system", "content": system_prompt}],
        "tools": _build_tools(),
        "fallbackModels": ["gpt-4o-mini"],
    }


def _build_assistant_payload(config: VapiAssistantConfig) -> dict:
    webhook_url = f"{settings.webhook_base_url}/api/webhooks/vapi"
    return {
        "name": config.name,
        "firstMessage": config.first_message,
        "serverUrl": webhook_url,
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2-phonecall",
            "language": "en",
            "smartFormat": True,
            "endpointing": 300,
        },
        "model": _build_model_block(config.system_prompt),
        "voice": _build_voice_block(config.voice_id),
        "firstMessageMode": "assistant-speaks-first",
        "startSpeakingPlan": {"waitSeconds": 0},
        "silenceTimeoutSeconds": 30,
        "responseDelaySeconds": 0,
        "llmRequestDelaySeconds": 0,
        "numWordsToInterruptAssistant": 3,
        "backgroundDenoisingEnabled": True,
        "endCallFunctionEnabled": True,
        "endCallPhrases": ["have a great day", "speak soon", "bye bye"],
        "maxDurationSeconds": config.max_call_duration_seconds,
    }


async def create_or_update_assistant(
    config: VapiAssistantConfig, assistant_id: str | None
) -> str:
    payload = _build_assistant_payload(config)
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        if assistant_id:
            resp = await client.patch(
                f"https://api.vapi.ai/assistant/{assistant_id}",
                json=payload,
                headers=headers,
                timeout=30,
            )
        else:
            resp = await client.post(
                "https://api.vapi.ai/assistant",
                json=payload,
                headers=headers,
                timeout=30,
            )
        if not resp.is_success:
            raise Exception(f"Vapi {resp.status_code}: {resp.text}")
        return resp.json()["id"]


async def trigger_call(phone_number: str, assistant_id: str) -> tuple[str, str, int, int]:
    """Returns (call_id, caller_display_number, pool_index_1based, pool_size)."""
    phone_id, caller_number, pool_idx, pool_size = _pick_from_pool(phone_number)
    label = f"Twilio (intl)" if pool_idx == 0 else f"pool {pool_idx}/{pool_size}"
    logger.warning("trigger_call → phoneNumberId=%r (%s)", phone_id, label)
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}", "Content-Type": "application/json"}
    payload: dict = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_id,
        "customer": {"number": phone_number},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.vapi.ai/call/phone",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if not resp.is_success:
            raise Exception(f"Vapi {resp.status_code}: {resp.text}")
        return resp.json()["id"], caller_number, pool_idx, pool_size


async def delete_assistant(assistant_id: str) -> None:
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"https://api.vapi.ai/assistant/{assistant_id}",
            headers=headers,
            timeout=15,
        )
        if not resp.is_success:
            raise Exception(f"Vapi {resp.status_code}: {resp.text}")


async def end_call(call_id: str) -> None:
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"https://api.vapi.ai/call/{call_id}",
            headers=headers,
            timeout=15,
        )
        if not resp.is_success:
            raise Exception(f"Vapi {resp.status_code}: {resp.text}")


async def get_call_status(call_id: str) -> str:
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.vapi.ai/call/{call_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status", "unknown")


async def get_call(call_id: str) -> dict:
    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.vapi.ai/call/{call_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
