"""
Notificaciones Telegram para el salón bot.
Envía un mensaje con botón "Confirmar cita" al dueño del salón.
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any

import httpx

# Almacén en memoria de citas pendientes de confirmar
# { key: {service, client_name, client_email, datetime_str} }
_pending: dict[str, dict] = {}


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def store_pending(service: str, client_name: str, client_email: str, datetime_str: str) -> str:
    """Guarda la cita y devuelve una clave corta para el callback."""
    key = secrets.token_hex(4)  # 8 chars, cabe en callback_data
    _pending[key] = {
        "service": service,
        "client_name": client_name,
        "client_email": client_email,
        "datetime_str": datetime_str,
    }
    return key


def get_pending(key: str) -> dict | None:
    return _pending.get(key)


def remove_pending(key: str) -> None:
    _pending.pop(key, None)


def send_booking_notification(key: str, service: str, client_name: str,
                               client_email: str, datetime_str: str) -> bool:
    token = _token()
    chat_id = _chat_id()
    if not token or not chat_id:
        return False

    text = (
        f"📅 *Nueva cita agendada*\n\n"
        f"👤 *Cliente:* {client_name}\n"
        f"📧 *Email:* {client_email}\n"
        f"✂️ *Servicio:* {service}\n"
        f"🕐 *Hora:* {datetime_str}\n\n"
        f"¿Envías confirmación al cliente?"
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Confirmar cita", "callback_data": f"confirm:{key}"},
            {"text": "❌ Cancelar",       "callback_data": f"cancel:{key}"},
        ]]
    }

    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(keyboard),
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def answer_callback(callback_query_id: str, text: str) -> None:
    token = _token()
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def edit_message_text(chat_id: str, message_id: int, text: str) -> None:
    token = _token()
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=5,
        )
    except Exception:
        pass
