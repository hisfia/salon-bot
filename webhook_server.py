"""
Servidor webhook para las herramientas del agente ElevenLabs.
Usa Google Calendar + notificaciones Telegram con botón de confirmación.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
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
async def crear_cita(request: Request):
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

        # Notificar al dueño del salón por Telegram
        try:
            from services.telegram_bot import store_pending, send_booking_notification
            key = store_pending(servicio, nombre, email, info["start"])
            send_booking_notification(key, servicio, nombre, email, info["start"])
        except Exception as te:
            print(f"[telegram] Error: {te}")

        return {
            "result": (
                f"¡Cita confirmada! {info['summary']} agendada para el "
                f"{info['start']}."
            )
        }
    except Exception as e:
        return {"result": f"Error al crear la cita: {e}"}


# ── Telegram webhook ───────────────────────────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    callback = update.get("callback_query")
    if not callback:
        return {"ok": True}

    callback_id   = callback["id"]
    data          = callback.get("data", "")
    chat_id       = str(callback["message"]["chat"]["id"])
    message_id    = callback["message"]["message_id"]

    from services.telegram_bot import (
        answer_callback, edit_message_text,
        get_pending, remove_pending,
    )

    if data.startswith("confirm:"):
        key = data.split(":", 1)[1]
        booking = get_pending(key)

        if not booking:
            answer_callback(callback_id, "Esta cita ya fue procesada.")
            return {"ok": True}

        # Intentar enviar email de confirmación
        from services.email_sender import send_confirmation_email
        import os
        salon_name = os.getenv("SALON_NAME", "Salón Belleza Total")

        email_sent = send_confirmation_email(
            client_name=booking["client_name"],
            client_email=booking["client_email"],
            service=booking["service"],
            datetime_str=booking["datetime_str"],
            salon_name=salon_name,
        )

        remove_pending(key)

        if email_sent:
            answer_callback(callback_id, "✅ Email de confirmación enviado")
            edit_message_text(chat_id, message_id,
                f"✅ *Cita confirmada*\n\n"
                f"👤 {booking['client_name']} — {booking['service']}\n"
                f"🕐 {booking['datetime_str']}\n\n"
                f"📧 Email enviado a {booking['client_email']}"
            )
        else:
            answer_callback(callback_id, "⚠️ Cita confirmada, pero email no configurado")
            edit_message_text(chat_id, message_id,
                f"✅ *Cita confirmada* (sin email — configura GMAIL\\_APP\\_PASSWORD)\n\n"
                f"👤 {booking['client_name']} — {booking['service']}\n"
                f"🕐 {booking['datetime_str']}"
            )

    elif data.startswith("cancel:"):
        key = data.split(":", 1)[1]
        booking = get_pending(key)
        remove_pending(key)

        answer_callback(callback_id, "Cita marcada como cancelada")
        name = booking["client_name"] if booking else "cliente"
        edit_message_text(chat_id, message_id,
            f"❌ *Cita cancelada*\n\n👤 {name}"
        )

    return {"ok": True}


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
