import logging
import httpx
from models import BookMeetingToolPayload
from config import settings

logger = logging.getLogger("calcom")

CALCOM_BASE = "https://api.cal.com/v2"
CALCOM_API_VERSION = "2024-08-13"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.calcom_api_key}",
        "cal-api-version": CALCOM_API_VERSION,
        "Content-Type": "application/json",
    }


async def book_slot(payload: BookMeetingToolPayload) -> dict:
    logger.warning("Cal.com booking attempt | datetime=%s | timezone=%s | attendee=%s",
                   payload.meeting_datetime_iso, payload.timezone, payload.attendee_email)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CALCOM_BASE}/bookings",
            headers=_headers(),
            json={
                "eventTypeId": int(settings.calcom_event_type_id),
                "start": payload.meeting_datetime_iso,
                "attendee": {
                    "name": payload.attendee_name,
                    "email": str(payload.attendee_email),
                    "timeZone": payload.timezone,
                },
            },
            timeout=30,
        )
        if not resp.is_success:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            msg = (body.get("error") or {}).get("message", "") or body.get("message", "")
            logger.warning("Cal.com booking failed | status=%s | body=%s", resp.status_code, resp.text[:1000])
            if "not available" in msg.lower() or "already has booking" in msg.lower():
                raise Exception("slot not available")
            raise Exception(f"Cal.com {resp.status_code}: {msg or resp.text}")
        return resp.json().get("data", resp.json())
