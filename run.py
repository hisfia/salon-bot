"""
Ejecuta el agente de voz del salón de belleza usando ElevenLabs Conversational AI.

Uso:
  python run.py            # modo voz (micrófono + altavoces)
  python run.py --test     # modo texto (teclado, sin micrófono)

Requiere haber ejecutado antes:  python setup_agent.py
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time

from dotenv import load_dotenv
from rich.console import Console

# Recargar .env para incluir ELEVENLABS_AGENT_ID guardado por setup_agent.py
load_dotenv(override=True)

console = Console()


# ── Herramientas Google Calendar (ejecutadas localmente) ──────────────────────

def _handle_obtener_horarios_disponibles(params: dict) -> str:
    from services.google_calendar import get_available_slots
    fecha    = params.get("fecha", "mañana")
    duracion = int(params.get("duracion_min", 60))
    try:
        slots = get_available_slots(fecha, duracion_min=duracion)
        if not slots:
            return f"No hay horarios disponibles el {fecha}."
        lines = [f"{i+1}. {s['display']}" for i, s in enumerate(slots)]
        return "Horarios disponibles:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error al consultar el calendario: {e}"


def _handle_crear_cita(params: dict) -> str:
    from services.google_calendar import create_appointment
    servicio = params.get("servicio", "Consulta")
    nombre   = params.get("nombre_cliente", "")
    email    = params.get("email_cliente", "")
    inicio   = params.get("fecha_hora", "")
    duracion = int(params.get("duracion_min", 60))
    if not all([nombre, email, inicio]):
        return "Faltan datos: necesito nombre, email y fecha_hora."
    try:
        info = create_appointment(servicio, nombre, email, inicio, duracion)
        return (
            f"¡Cita confirmada! {info['summary']} agendada para el "
            f"{info['start']}. Invitación enviada a {email}."
        )
    except Exception as e:
        return f"Error al crear la cita: {e}"


TOOL_HANDLERS = {
    "obtener_horarios_disponibles": _handle_obtener_horarios_disponibles,
    "crear_cita": _handle_crear_cita,
}


# ── Constructor de la conversación ────────────────────────────────────────────

def build_conversation(test_mode: bool):
    """Construye el objeto Conversation con los handlers y callbacks correctos."""
    import config
    from elevenlabs import ElevenLabs
    from elevenlabs.conversational_ai.conversation import Conversation, ClientTools

    agent_id = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
    if not agent_id:
        console.print(
            "[bold red]✗ ELEVENLABS_AGENT_ID no encontrado en .env.\n"
            "  Ejecuta primero:  python setup_agent.py[/]"
        )
        sys.exit(1)

    # Registrar herramientas Calendly como client tools
    client_tools = ClientTools()
    for name, handler in TOOL_HANDLERS.items():
        client_tools.register(name, handler)

    elevenlabs_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    conversation = Conversation(
        client=elevenlabs_client,
        agent_id=agent_id,
        requires_auth=False,
        audio_interface=None if test_mode else _get_audio_interface(),
        client_tools=client_tools,
        callback_agent_response=_on_agent_response,
        callback_user_transcript=_on_user_transcript,
        callback_latency_measurement=lambda ms: None,  # silenciar métricas
        callback_end_session=_on_session_end,
    )
    return conversation


def _get_audio_interface():
    try:
        from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
        return DefaultAudioInterface()
    except ImportError:
        console.print("[yellow]⚠ pyaudio no instalado. Cámbiando a modo texto.[/]")
        return None


# ── Callbacks de la conversación ──────────────────────────────────────────────

_session_ended = threading.Event()


def _on_agent_response(text: str) -> None:
    console.print(f"\n[bold cyan]🤖 Valeria:[/] {text}\n")


def _on_user_transcript(text: str) -> None:
    if text.strip():
        console.print(f"[dim](Transcripción): {text}[/dim]")


def _on_session_end() -> None:
    console.print("\n[bold]Sesión terminada.[/]")
    _session_ended.set()


# ── Modo texto (test) ─────────────────────────────────────────────────────────

def run_text_mode(conversation) -> None:
    """Bucle de texto: lee desde teclado y envía mensajes de texto al agente."""
    from rich.prompt import Prompt

    conversation.start_session()

    # Dar tiempo al agente para que envíe el primer mensaje
    time.sleep(2.5)

    console.print("[dim]Escribe tu mensaje y presiona Enter. Escribe [bold]salir[/] para terminar.[/dim]\n")

    try:
        while not _session_ended.is_set():
            user_input = Prompt.ask("[bold green]👤 Tú[/]").strip()

            if not user_input:
                continue
            if user_input.lower() in {"salir", "exit", "quit", "adiós", "adios"}:
                break

            conversation.send_user_message(user_input)

            # Esperar respuesta del agente antes del siguiente prompt
            time.sleep(3)

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        conversation.end_session()
        _session_ended.wait(timeout=3)


# ── Modo voz ──────────────────────────────────────────────────────────────────

def run_voice_mode(conversation) -> None:
    """Modo voz: micrófono + altavoces via DefaultAudioInterface."""
    console.print("[dim]Habla cuando quieras. Presiona [bold]Ctrl+C[/] para terminar.[/dim]\n")

    conversation.start_session()

    def _handle_sigint(sig, frame):
        console.print("\n[yellow]Terminando…[/]")
        conversation.end_session()

    signal.signal(signal.SIGINT, _handle_sigint)

    conversation.wait_for_session_end()


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agente de voz – Salón de Belleza")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--test", action="store_true", help="Modo texto (sin micrófono)")
    group.add_argument("--voice", action="store_true", help="Modo voz (micrófono + TTS)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determinar modo: prioridad flags > TEST_MODE del .env
    if args.test:
        test_mode = True
    elif args.voice:
        test_mode = False
    else:
        test_mode = os.getenv("TEST_MODE", "true").lower() == "true"

    import config
    console.rule(f"[bold magenta]{config.SALON_NAME}[/]")
    console.print(
        f"  Agente: [bold]{os.getenv('ELEVENLABS_AGENT_ID', '(no configurado)')}[/]\n"
        f"  Modo:   [bold]{'Texto (test)' if test_mode else 'Voz'}[/]\n"
    )

    conversation = build_conversation(test_mode=test_mode)

    if test_mode:
        run_text_mode(conversation)
    else:
        run_voice_mode(conversation)


if __name__ == "__main__":
    main()
