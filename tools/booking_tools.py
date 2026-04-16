"""
Definición de herramientas (tools) que Claude puede invocar
para gestionar la agenda del salón.
"""

from __future__ import annotations

from typing import Any

# ── Esquemas para la API de Claude ────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_services",
        "description": (
            "Obtiene la lista de servicios disponibles en el salón "
            "(corte, tinte, manicura, etc.) junto con su duración."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_available_slots",
        "description": (
            "Devuelve los próximos horarios libres para un servicio específico. "
            "Llama a esta herramienta después de que el cliente haya elegido servicio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type_uri": {
                    "type": "string",
                    "description": "URI del tipo de evento obtenido de get_services.",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Cuántos días hacia adelante buscar (default 7).",
                    "default": 7,
                },
            },
            "required": ["event_type_uri"],
        },
    },
    {
        "name": "create_booking_link",
        "description": (
            "Crea un enlace de reserva único de Calendly para que el cliente "
            "confirme su cita. Úsalo cuando el cliente haya elegido el horario."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type_uri": {
                    "type": "string",
                    "description": "URI del tipo de evento.",
                },
            },
            "required": ["event_type_uri"],
        },
    },
]


# ── Ejecutor de herramientas ───────────────────────────────────────────

def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Despacha la llamada de herramienta al servicio correspondiente."""
    from services.calendly import CalendlyClient, CalendlyError

    client = CalendlyClient()

    try:
        if name == "get_services":
            services = client.get_event_types()
            if not services:
                return "No hay servicios configurados en Calendly."
            lines = [f"- {s['name']} ({s['duration_min']} min) | uri: {s['uri']}" for s in services]
            return "Servicios disponibles:\n" + "\n".join(lines)

        elif name == "get_available_slots":
            slots = client.get_available_slots(
                event_type_uri=tool_input["event_type_uri"],
                days_ahead=tool_input.get("days_ahead", 7),
            )
            if not slots:
                return "No hay horarios disponibles en los próximos días."
            lines = [f"{i+1}. {s['display']}" for i, s in enumerate(slots)]
            return "Horarios disponibles:\n" + "\n".join(lines)

        elif name == "create_booking_link":
            url = client.create_scheduling_link(tool_input["event_type_uri"])
            return f"Enlace de reserva generado: {url}"

        else:
            return f"Herramienta desconocida: {name}"

    except CalendlyError as exc:
        return f"Error al consultar Calendly: {exc}"
