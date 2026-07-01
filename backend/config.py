from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    vapi_api_key: str = ""
    vapi_webhook_secret: str = ""           # optional — set to verify Vapi HMAC signatures
    vapi_intl_phone_number_id: str = ""     # international calls fallback (Twilio-backed number)
    vapi_phone_number_ids: str = ""         # comma-separated pool of phone number IDs
    vapi_phone_numbers: str = ""            # comma-separated pool of display strings (same order)
    calcom_api_key: str = ""
    calcom_event_type_id: str = ""
    webhook_base_url: str = "http://localhost:8000"
    debug_secret: str = ""                  # optional — protects /webhooks/debug endpoint


settings = Settings()
