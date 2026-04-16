"""
Cliente para Google Calendar API v3 usando Service Account.

Pasos para configurar (una sola vez):
  1. Ve a https://console.cloud.google.com
  2. Crea un proyecto → habilita "Google Calendar API"
  3. IAM → Service Accounts → Crear cuenta de servicio
  4. Descarga la clave JSON → guárdala como credentials.json en la raíz del proyecto
  5. Abre Google Calendar → Configuración del calendario → Compartir con personas específicas
     → agrega el email del service account con permiso "Realizar cambios en eventos"
  6. En .env pon GOOGLE_CALENDAR_ID=tu_email@gmail.com (o el ID del calendario)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    import os, base64, json as _json
    # Prioridad: variable de entorno base64 (Railway/cloud) → archivo local
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if raw:
        info = _json.loads(base64.b64decode(raw).decode())
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
    return build("calendar", "v3", credentials=creds)


# ── Slots disponibles ──────────────────────────────────────────────────────────

def get_available_slots(date_str: str, duration_min: int = 60) -> list[dict[str, str]]:
    """
    Devuelve los horarios libres de un día dado.

    date_str: "2026-04-17" (ISO)  o  "mañana" / "pasado mañana" / "lunes" (texto)
    Retorna lista de {"start": "ISO", "display": "Viernes 17/04 10:00"}
    """
    tz = ZoneInfo(config.SALON_TIMEZONE)
    target_date = _parse_date(date_str, tz)

    if target_date is None:
        return []

    # Ventana de búsqueda: todo el día en horario del salón
    day_start = datetime(target_date.year, target_date.month, target_date.day,
                         config.OPEN_HOUR, 0, tzinfo=tz)
    day_end   = datetime(target_date.year, target_date.month, target_date.day,
                         config.CLOSE_HOUR, 0, tzinfo=tz)

    # No mostrar horarios ya pasados
    now = datetime.now(tz) + timedelta(minutes=30)
    if day_start < now:
        day_start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
        if now.minute >= 30:
            day_start += timedelta(minutes=30)

    if day_start >= day_end:
        return []

    # Obtener eventos existentes ese día
    service = _get_service()
    events_result = service.events().list(
        calendarId=config.GOOGLE_CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    busy_blocks = [
        (
            _parse_dt(e["start"].get("dateTime", e["start"].get("date"))),
            _parse_dt(e["end"].get("dateTime",   e["end"].get("date"))),
        )
        for e in events_result.get("items", [])
    ]

    # Generar slots cada `duration_min` minutos dentro del horario
    slots = []
    cursor = day_start
    while cursor + timedelta(minutes=duration_min) <= day_end:
        slot_end = cursor + timedelta(minutes=duration_min)
        if not _overlaps(cursor, slot_end, busy_blocks):
            slots.append({
                "start": cursor.isoformat(),
                "display": cursor.strftime("%A %d/%m/%Y  %H:%M"),
            })
        cursor += timedelta(minutes=duration_min)

    return slots[:10]


# ── Crear cita ─────────────────────────────────────────────────────────────────

def create_appointment(
    service_name: str,
    client_name: str,
    client_email: str,
    start_iso: str,
    duration_min: int = 60,
) -> dict[str, str]:
    """
    Crea un evento en Google Calendar y envía invitación al cliente.
    Retorna {"event_link": "...", "summary": "..."}
    """
    tz = ZoneInfo(config.SALON_TIMEZONE)
    parsed = datetime.fromisoformat(start_iso)
    # Si no tiene timezone, asumir que ya es hora local del salón
    if parsed.tzinfo is None:
        start_dt = parsed.replace(tzinfo=tz)
    else:
        start_dt = parsed.astimezone(tz)
    end_dt = start_dt + timedelta(minutes=duration_min)

    event = {
        "summary": f"{service_name} – {client_name}",
        "description": (
            f"Servicio: {service_name}\n"
            f"Cliente: {client_name}\n"
            f"Email: {client_email}\n"
            f"Agendado por: Agente de voz {config.SALON_NAME}"
        ),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": config.SALON_TIMEZONE},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": config.SALON_TIMEZONE},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    gcal_service = _get_service()
    created = gcal_service.events().insert(
        calendarId=config.GOOGLE_CALENDAR_ID,
        body=event,
    ).execute()

    return {
        "event_link": created.get("htmlLink", ""),
        "summary": created.get("summary", ""),
        "start": start_dt.strftime("%A %d/%m/%Y a las %H:%M"),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

_DAY_NAMES_ES = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
}

def _parse_date(text: str, tz: ZoneInfo):
    """Convierte texto a date. Acepta ISO (2026-04-17) o español relativo."""
    from datetime import date
    text = text.strip().lower()
    today = datetime.now(tz).date()

    if text in ("hoy", "today"):
        return today
    if text in ("mañana", "manana", "tomorrow"):
        return today + timedelta(days=1)
    if text in ("pasado mañana", "pasado manana"):
        return today + timedelta(days=2)
    # Nombre de día en español
    if text in _DAY_NAMES_ES:
        target_wd = _DAY_NAMES_ES[text]
        days_ahead = (target_wd - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    # ISO
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_dt(dt_str: str) -> datetime:
    if "T" in dt_str:
        return datetime.fromisoformat(dt_str)
    # fecha sin hora → asumir medianoche UTC
    return datetime.fromisoformat(dt_str + "T00:00:00+00:00")


def _overlaps(start: datetime, end: datetime, blocks: list) -> bool:
    for b_start, b_end in blocks:
        if start < b_end and end > b_start:
            return True
    return False
