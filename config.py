"""Carga y valida todas las variables de entorno del proyecto."""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Variable de entorno requerida no encontrada: {key}\n"
            f"Copia .env.example a .env y completa los valores."
        )
    return value


# ── Anthropic ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ── ElevenLabs ───────────────────────────────────────────────────────
ELEVENLABS_API_KEY: str = _require("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

# ── Google Calendar ───────────────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json")
GOOGLE_CALENDAR_ID: str          = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SALON_TIMEZONE: str              = os.getenv("SALON_TIMEZONE", "America/Mexico_City")
OPEN_HOUR: int                   = int(os.getenv("OPEN_HOUR", "9"))
CLOSE_HOUR: int                  = int(os.getenv("CLOSE_HOUR", "19"))

# ── Calendly (legacy, ya no requerido) ───────────────────────────────
CALENDLY_API_KEY: str  = os.getenv("CALENDLY_API_KEY", "")
CALENDLY_USER_URI: str = os.getenv("CALENDLY_USER_URI", "")
CALENDLY_BASE_URL: str = "https://api.calendly.com"

# ── ElevenLabs Conversational AI ─────────────────────────────────────
# Opcional hasta que se ejecute setup_agent.py
ELEVENLABS_AGENT_ID: str = os.getenv("ELEVENLABS_AGENT_ID", "")

# ── App ──────────────────────────────────────────────────────────────
TEST_MODE: bool = os.getenv("TEST_MODE", "true").lower() == "true"
SALON_NAME: str = os.getenv("SALON_NAME", "Salón Belleza Total")
CLAUDE_MODEL: str = "claude-sonnet-4-6"
