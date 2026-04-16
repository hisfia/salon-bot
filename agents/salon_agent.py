"""
Agente principal del salón de belleza.

Flujo de conversación:
  1. Saluda al cliente
  2. Consulta qué servicio desea
  3. Muestra horarios disponibles (via Calendly)
  4. Genera enlace de reserva
  5. Despide al cliente

Claude actúa como orquestador: decide cuándo llamar las herramientas
y qué decirle al cliente en cada paso.
"""

from __future__ import annotations

import anthropic

import config
from services.voice import speak
from services.speech_input import listen
from tools.booking_tools import TOOLS, execute_tool

SYSTEM_PROMPT = f"""
Eres la recepcionista virtual de {config.SALON_NAME}.
Tu nombre es Valeria. Hablas en español, eres amable, profesional y concisa.

OBJETIVO: Ayudar al cliente a agendar una cita en el salón.

FLUJO:
1. Saluda y pregunta en qué puedes ayudar.
2. Cuando el cliente mencione un servicio, usa get_services para confirmar
   que existe y obtener su URI.
3. Usa get_available_slots para mostrar hasta 5 horarios disponibles.
4. Cuando el cliente elija un horario, usa create_booking_link y
   dile la URL para confirmar su cita.
5. Despídete amablemente.

REGLAS:
- Respuestas cortas (2-3 oraciones máximo).
- Si el cliente pregunta algo fuera del agendado, redirige con amabilidad.
- Nunca inventes horarios; solo muestra los que devuelva get_available_slots.
- Si hay un error de Calendly, disculpate y sugiere llamar al salón.
"""


class SalonAgent:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._history: list[dict] = []

    # ── bucle principal ─────────────────────────────────────────────────

    def run(self) -> None:
        speak(f"Hola, bienvenido a {config.SALON_NAME}. Soy Valeria, ¿en qué te puedo ayudar hoy?")

        while True:
            user_text = listen("Tú")
            if not user_text:
                continue
            if user_text.lower() in {"salir", "exit", "quit", "adiós", "adios"}:
                speak("Hasta pronto, que tengas un excelente día.")
                break

            self._history.append({"role": "user", "content": user_text})
            response_text = self._call_claude()
            speak(response_text)

    # ── lógica Claude con herramientas ──────────────────────────────────

    def _call_claude(self) -> str:
        """
        Envía el historial a Claude y resuelve todas las llamadas
        a herramientas hasta obtener una respuesta de texto final.
        """
        while True:
            response = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self._history,
                # Prompt caching en el system prompt (reduce costos)
                betas=["prompt-caching-2024-07-31"],
            )

            # Si Claude quiere usar herramientas
            if response.stop_reason == "tool_use":
                # Añadir el bloque completo de Claude al historial
                self._history.append(
                    {"role": "assistant", "content": response.content}
                )

                # Ejecutar cada herramienta y devolver resultados
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = execute_tool(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                self._history.append({"role": "user", "content": tool_results})
                # Vuelve a llamar a Claude con los resultados
                continue

            # Respuesta de texto final
            text = next(
                (b.text for b in response.content if hasattr(b, "text")),
                "Lo siento, no pude procesar tu solicitud.",
            )
            self._history.append({"role": "assistant", "content": text})
            return text
