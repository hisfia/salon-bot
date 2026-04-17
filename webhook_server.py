"""
Servidor webhook para las herramientas del agente ElevenLabs.
Usa Google Calendar + notificaciones Telegram con botón de confirmación.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
from fastapi import FastAPI, BackgroundTasks, Request
import uvicorn

app = FastAPI(title="Salon Bot Webhooks")


# ── Herramientas ElevenLabs ────────────────────────────────────────────────────

@app.post("/obtener_horarios_disponibles")
async def obtener_horarios_disponibles(request: Request):
    body = await request.json()
    fecha    = body.get("fecha", "mañana")
    duracion = int(body.get("duracion_min", 30))

    try:
        from services.google_calendar import get_available_slots
        slots = get_available_slots(fecha, duration_min=duracion)
        if not slots:
            return {"result": f"No hay horarios disponibles el {fecha}."}
        lines = [f"{i+1}. {s['display']}" for i, s in enumerate(slots)]
        return {"result": "Horarios disponibles:\n" + "\n".join(lines)}
    except Exception as e:
        return {"result": f"Error al consultar el calendario: {e}"}


@app.post("/crear_cita")
async def crear_cita(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    servicio   = body.get("servicio", "Consulta")
    nombre     = body.get("nombre_cliente", "")
    email      = body.get("email_cliente", "")
    fecha_hora = body.get("fecha_hora", "")
    duracion   = int(body.get("duracion_min", 30))

    if not all([nombre, email, fecha_hora]):
        return {"result": "Faltan datos: necesito nombre, email y fecha_hora."}

    try:
        from services.google_calendar import create_appointment
        info = create_appointment(servicio, nombre, email, fecha_hora, duracion)

        # Notificar al dueño por Telegram (en segundo plano para no bloquear)
        background_tasks.add_task(_notify_telegram, servicio, nombre, email, info["start"])

        return {
            "result": (
                f"¡Cita confirmada! {info['summary']} agendada para el "
                f"{info['start']}."
            )
        }
    except Exception as e:
        return {"result": f"Error al crear la cita: {e}"}


def _notify_telegram(servicio: str, nombre: str, email: str, datetime_str: str):
    try:
        from services.telegram_bot import store_pending, send_booking_notification
        key = store_pending(servicio, nombre, email, datetime_str)
        send_booking_notification(key, servicio, nombre, email, datetime_str)
    except Exception as e:
        print(f"[telegram] Error: {e}")


# ── Telegram webhook ───────────────────────────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    update = await request.json()

    callback = update.get("callback_query")
    if not callback:
        return {"ok": True}

    callback_id = callback["id"]
    data        = callback.get("data", "")
    chat_id     = str(callback["message"]["chat"]["id"])
    message_id  = callback["message"]["message_id"]

    from services.telegram_bot import answer_callback, get_pending

    if data.startswith("confirm:"):
        key = data.split(":", 1)[1]
        booking = get_pending(key)

        if not booking:
            answer_callback(callback_id, "Esta cita ya fue procesada.")
            return {"ok": True}

        # Responder a Telegram inmediatamente
        answer_callback(callback_id, "⏳ Enviando confirmación...")

        # Procesar email en segundo plano
        background_tasks.add_task(_confirm_booking, key, booking, chat_id, message_id)

    elif data.startswith("cancel:"):
        key = data.split(":", 1)[1]
        from services.telegram_bot import get_pending, remove_pending, edit_message_text
        booking = get_pending(key)
        remove_pending(key)
        answer_callback(callback_id, "Cita cancelada")
        name = booking["client_name"] if booking else "cliente"
        edit_message_text(chat_id, message_id, f"❌ *Cita cancelada*\n\n👤 {name}")

    return {"ok": True}


def _confirm_booking(key: str, booking: dict, chat_id: str, message_id: int):
    from services.telegram_bot import remove_pending, edit_message_text
    from services.email_sender import send_confirmation_email

    salon_name = os.getenv("SALON_NAME", "Salón Belleza Total")
    remove_pending(key)

    email_sent = send_confirmation_email(
        client_name=booking["client_name"],
        client_email=booking["client_email"],
        service=booking["service"],
        datetime_str=booking["datetime_str"],
        salon_name=salon_name,
    )

    if email_sent:
        edit_message_text(chat_id, message_id,
            f"✅ *Cita confirmada*\n\n"
            f"👤 {booking['client_name']} — {booking['service']}\n"
            f"🕐 {booking['datetime_str']}\n\n"
            f"📧 Email enviado a {booking['client_email']}"
        )
    else:
        print(f"[email] Fallo al enviar a {booking['client_email']}")
        edit_message_text(chat_id, message_id,
            f"✅ *Cita confirmada* ⚠️ Email no enviado\n\n"
            f"👤 {booking['client_name']} — {booking['service']}\n"
            f"🕐 {booking['datetime_str']}\n"
            f"📧 {booking['client_email']}"
        )


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
