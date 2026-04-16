"""
Servidor webhook para las herramientas del agente ElevenLabs.
Ahora usa Google Calendar (sin Calendly).

Arrancar:
    python webhook_server.py
Exponer públicamente (en otra terminal):
    python start.py
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
import uvicorn

app = FastAPI(title="Salon Bot Webhooks – Google Calendar")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/obtener_horarios_disponibles")
async def obtener_horarios_disponibles(request: Request):
    """Devuelve horarios libres para una fecha dada."""
    body = await request.json()
    fecha     = body.get("fecha", "mañana")
    duracion  = int(body.get("duracion_min", 60))

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
    """Crea la cita en Google Calendar y envía confirmación al cliente."""
    body = await request.json()
    servicio      = body.get("servicio", "Consulta")
    nombre        = body.get("nombre_cliente", "")
    email         = body.get("email_cliente", "")
    fecha_hora    = body.get("fecha_hora", "")   # ISO: "2026-04-17T10:00:00"
    duracion      = int(body.get("duracion_min", 60))

    if not all([nombre, email, fecha_hora]):
        return {"result": "Faltan datos: necesito nombre, email y fecha_hora."}

    try:
        from services.google_calendar import create_appointment
        info = create_appointment(servicio, nombre, email, fecha_hora, duracion)
        return {
            "result": (
                f"¡Cita confirmada! {info['summary']} agendada para el "
                f"{info['start']}. Se envió una invitación al correo {email}."
            )
        }
    except Exception as e:
        return {"result": f"Error al crear la cita: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
