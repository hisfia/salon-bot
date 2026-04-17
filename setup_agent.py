"""
Crea (o actualiza) el agente de voz en ElevenLabs con Google Calendar.

Modos:
  python setup_agent.py                         # client tools (run.py local)
  python setup_agent.py --webhook <URL_BASE>    # webhook tools (ElevenLabs web)
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import config

from elevenlabs import ElevenLabs
from elevenlabs.types import (
    AgentConfig,
    ConversationalConfig,
    ObjectJsonSchemaPropertyInput,
    PromptAgentApiModelOutput,
    ToolRequestModel,
)
from elevenlabs.types.tool_request_model_tool_config import (
    ToolRequestModelToolConfig_Client,
    ToolRequestModelToolConfig_Webhook,
)
from elevenlabs.types import WebhookToolApiSchemaConfigInput
from rich.console import Console

console = Console()

# ── Prompt del sistema ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""
Eres Valeria, la recepcionista del {config.SALON_NAME}. Hablas en español de España, con un tono cercano, natural y profesional — como una persona real, no un robot. Usas expresiones como "claro que sí", "perfecto", "estupendo", "por supuesto". Nunca suenas fría ni robótica.

SERVICIOS Y DURACIÓN:
  • Corte dama: 60 min
  • Corte caballero: 30 min
  • Tinte y decoloración: 120 min
  • Keratina / hidratación: 90 min
  • Manicura: 45 min
  • Pedicura: 60 min
  • Maquillaje y cejas: 45 min

HORARIO: Lunes a sábado, de {config.OPEN_HOUR}:00 a {config.CLOSE_HOUR}:00. Domingos cerrado.

━━━ FLUJO DE CONVERSACIÓN ━━━

Sigue estos pasos en orden. Nunca te saltes ninguno.

PASO 1 — SERVICIO
Pregunta qué servicio desea. Si el cliente no sabe o pregunta qué hay disponible, léele la lista con naturalidad.
Si el servicio no está en la lista, dile amablemente que no lo ofrecéis y sugiere el más parecido.

PASO 2 — FECHA
Pregunta para qué día. Acepta cualquier formato: "mañana", "el viernes", "el 23", fechas exactas.
Si dice un domingo o festivo, avisa que estáis cerrados y ofrece el lunes siguiente.

PASO 3 — CONSULTAR DISPONIBILIDAD
Llama a obtener_horarios_disponibles con la fecha y la duración del servicio elegido.
→ Si hay huecos: preséntale máximo 5 opciones de forma natural. Ejemplo: "Tenemos las diez de la mañana, las once y media, las tres de la tarde o las cinco. ¿Cuál te va mejor?"
→ Si no hay huecos: dile que ese día está completo y pregunta si quiere otro día.

PASO 4 — HORA
Cuando el cliente elija hora, confírmala antes de continuar. Ejemplo: "Perfecto, las cinco de la tarde del viernes. ¿Te viene bien?"

PASO 5 — DATOS PERSONALES
Pide el nombre completo. Luego el correo electrónico (deletréalo si hay dudas).

PASO 6 — CREAR CITA
Llama a crear_cita con todos los datos. Usa SIEMPRE el valor "start" ISO exacto devuelto por obtener_horarios_disponibles — nunca construyas la fecha/hora manualmente.

PASO 7 — CONFIRMACIÓN
Confirma la cita con todos los detalles: nombre, servicio, día y hora. Ejemplo: "¡Listo, María! Tu cita para el corte de dama está confirmada para el viernes 18 de abril a las cinco de la tarde. Te esperamos 😊"

━━━ CONVERSIÓN DE HORAS ━━━
Convierte siempre a formato 24h para las herramientas:
  "las 5 de la tarde" → 17:00 | "las 6 y media de la tarde" → 18:30
  "las 10 de la mañana" → 10:00 | "mediodía" → 12:00 | "las 2" (sin contexto, tarde) → 14:00

━━━ REGLAS IMPORTANTES ━━━
  • Respuestas cortas: 1-3 frases máximo. No hagas monólogos.
  • SIEMPRE consulta disponibilidad antes de confirmar cualquier hora, aunque el cliente ya la haya dicho.
  • Nunca ofrezcas horas que no aparezcan en obtener_horarios_disponibles.
  • Si el cliente pregunta por precios, dile que con gusto le informa el equipo del salón y que de momento puedes ayudarle a reservar su cita.
  • Si el cliente quiere cambiar o cancelar una cita existente, dile que lo gestione llamando directamente al salón.
  • Zona horaria: {config.SALON_TIMEZONE}.
""".strip()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _params(properties: dict, required: list) -> ObjectJsonSchemaPropertyInput:
    return ObjectJsonSchemaPropertyInput(type="object", properties=properties, required=required)


def _build_client_tools() -> list[ToolRequestModel]:
    return [
        ToolRequestModel(
            tool_config=ToolRequestModelToolConfig_Client(
                type="client",
                name="obtener_horarios_disponibles",
                description=(
                    "Consulta el calendario del salón y devuelve los horarios libres "
                    "para una fecha específica. Llama esto antes de proponer horarios al cliente."
                ),
                parameters=_params(
                    properties={
                        "fecha":       {"type": "string", "description": "Fecha en ISO (2026-04-17) o texto: 'mañana', 'viernes', etc."},
                        "duracion_min": {"type": "integer", "description": "Duración del servicio en minutos."},
                    },
                    required=["fecha"],
                ),
                expects_response=True,
                response_timeout_secs=30,
            )
        ),
        ToolRequestModel(
            tool_config=ToolRequestModelToolConfig_Client(
                type="client",
                name="crear_cita",
                description=(
                    "Crea la cita directamente en Google Calendar y envía una invitación "
                    "por email al cliente. Úsalo solo cuando tengas: servicio, nombre, email y horario."
                ),
                parameters=_params(
                    properties={
                        "servicio":       {"type": "string",  "description": "Nombre del servicio (ej: Corte de cabello dama)."},
                        "nombre_cliente": {"type": "string",  "description": "Nombre completo del cliente."},
                        "email_cliente":  {"type": "string",  "description": "Correo electrónico del cliente."},
                        "fecha_hora":     {"type": "string",  "description": "Fecha y hora en ISO: 2026-04-17T10:00:00"},
                        "duracion_min":   {"type": "integer", "description": "Duración en minutos."},
                    },
                    required=["servicio", "nombre_cliente", "email_cliente", "fecha_hora"],
                ),
                expects_response=True,
                response_timeout_secs=30,
            )
        ),
    ]


def _build_webhook_tools(base_url: str) -> list[ToolRequestModel]:
    base = base_url.rstrip("/")
    return [
        ToolRequestModel(
            tool_config=ToolRequestModelToolConfig_Webhook(
                type="webhook",
                name="obtener_horarios_disponibles",
                description=(
                    "Consulta el calendario del salón y devuelve los horarios libres "
                    "para una fecha específica. Llama esto antes de proponer horarios al cliente."
                ),
                api_schema=WebhookToolApiSchemaConfigInput(
                    url=f"{base}/obtener_horarios_disponibles",
                    method="POST",
                    request_body_schema=_params(
                        properties={
                            "fecha":        {"type": "string",  "description": "Fecha ISO (2026-04-17) o texto: 'mañana', 'viernes'."},
                            "duracion_min": {"type": "integer", "description": "Duración del servicio en minutos."},
                        },
                        required=["fecha"],
                    ),
                ),
            )
        ),
        ToolRequestModel(
            tool_config=ToolRequestModelToolConfig_Webhook(
                type="webhook",
                name="crear_cita",
                description=(
                    "Crea la cita directamente en Google Calendar y envía una invitación "
                    "por email al cliente. Úsalo solo cuando tengas: servicio, nombre, email y horario."
                ),
                api_schema=WebhookToolApiSchemaConfigInput(
                    url=f"{base}/crear_cita",
                    method="POST",
                    request_body_schema=_params(
                        properties={
                            "servicio":       {"type": "string",  "description": "Nombre del servicio."},
                            "nombre_cliente": {"type": "string",  "description": "Nombre completo del cliente."},
                            "email_cliente":  {"type": "string",  "description": "Correo electrónico del cliente."},
                            "fecha_hora":     {"type": "string",  "description": "ISO: 2026-04-17T10:00:00"},
                            "duracion_min":   {"type": "integer", "description": "Duración en minutos."},
                        },
                        required=["servicio", "nombre_cliente", "email_cliente", "fecha_hora"],
                    ),
                ),
            )
        ),
    ]


def _save_to_env(key: str, value: str) -> None:
    env_path = Path(".env")
    content = env_path.read_text()
    if f"{key}=" in content:
        content = re.sub(rf"{key}=.*", f"{key}={value}", content)
    else:
        content += f"\n{key}={value}\n"
    env_path.write_text(content)


def _delete_old_tools(client: ElevenLabs) -> None:
    OLD_NAMES = {
        "obtener_servicios", "obtener_horarios_disponibles",
        "crear_enlace_reserva", "crear_cita",
    }
    try:
        tools = client.conversational_ai.tools.get_all()
        for tool in getattr(tools, "tools", []):
            name = getattr(tool.tool_config, "name", "")
            if name in OLD_NAMES:
                client.conversational_ai.tools.delete(tool_id=tool.id)
                console.print(f"  [dim]Eliminada: {name}[/]")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook", metavar="URL", help="URL base del servidor webhook")
    args = parser.parse_args()

    webhook_url = args.webhook or ""
    mode = "webhook" if webhook_url else "client"

    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    console.print("\n[dim]Limpiando herramientas anteriores…[/]")
    _delete_old_tools(client)

    console.rule(f"[bold]Creando herramientas Google Calendar ({mode})[/]")
    tool_defs = _build_webhook_tools(webhook_url) if webhook_url else _build_client_tools()
    tool_ids: list[str] = []
    for tool_def in tool_defs:
        name = tool_def.tool_config.name  # type: ignore[union-attr]
        console.print(f"  → [cyan]{name}[/]")
        result = client.conversational_ai.tools.create(request=tool_def)
        tool_ids.append(result.id)

    conversation_cfg = ConversationalConfig(
        agent=AgentConfig(
            first_message=(
                f"¡Hola! Bienvenido a {config.SALON_NAME}. "
                "Soy Valeria, ¿en qué te puedo ayudar hoy?"
            ),
            language="es",
            prompt=PromptAgentApiModelOutput(
                prompt=SYSTEM_PROMPT,
                llm="claude-sonnet-4-6",
                tool_ids=tool_ids,
                temperature=0.7,
                max_tokens=300,
            ),
        ),
        tts={
            "model_id": "eleven_multilingual_v2",
            "voice_id": config.ELEVENLABS_VOICE_ID,
        },
        asr={"language": "es"},
    )

    existing_id = config.ELEVENLABS_AGENT_ID
    if existing_id:
        console.rule("[bold]Actualizando agente[/]")
        client.conversational_ai.agents.update(
            agent_id=existing_id,
            conversation_config=conversation_cfg,
            name=f"Agente {config.SALON_NAME}",
        )
        agent_id = existing_id
    else:
        console.rule("[bold]Creando agente[/]")
        agent = client.conversational_ai.agents.create(
            name=f"Agente {config.SALON_NAME}",
            conversation_config=conversation_cfg,
        )
        agent_id = agent.agent_id
        _save_to_env("ELEVENLABS_AGENT_ID", agent_id)

    console.print(f"\n[bold green]✓ Agente listo:[/] {agent_id}")

    if webhook_url:
        _save_to_env("WEBHOOK_BASE_URL", webhook_url)
        console.print(f"[bold green]✓ Webhook URL:[/] {webhook_url}")
        console.print("\n[bold]Abre ElevenLabs y prueba el agente.[/]\n")
    else:
        console.print("\n[bold]Ejecuta:[/] python run.py --test\n")


if __name__ == "__main__":
    main()
