"""
Captura de voz del usuario.

- TEST_MODE  → lee texto del teclado (sin micrófono ni API)
- Normal     → graba desde el micrófono y transcribe con ElevenLabs STT
"""

from __future__ import annotations

import config


def listen(prompt: str = "Tu turno") -> str:
    """Escucha al usuario y devuelve el texto transcrito."""
    if config.TEST_MODE:
        return _listen_text(prompt)
    return _listen_microphone()


# ── Modo texto ─────────────────────────────────────────────────────────

def _listen_text(prompt: str) -> str:
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    user_input = Prompt.ask(f"\n[bold green]👤 {prompt}[/]")
    return user_input.strip()


# ── Modo micrófono ─────────────────────────────────────────────────────

def _listen_microphone(
    duration_seconds: int = 6,
    sample_rate: int = 16_000,
) -> str:
    """
    Graba `duration_seconds` de audio y lo transcribe con ElevenLabs STT.
    """
    import io
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from elevenlabs import ElevenLabs
    from rich.console import Console

    console = Console()
    console.print(f"[yellow]🎙 Grabando {duration_seconds}s… habla ahora[/]")

    recording = sd.rec(
        int(duration_seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    console.print("[yellow]⏹ Listo[/]")

    # Convertir a WAV en memoria
    buf = io.BytesIO()
    sf.write(buf, recording, sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)

    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
    result = client.speech_to_text.convert(
        file=("audio.wav", buf, "audio/wav"),
        model_id="scribe_v1",
        language_code="es",
    )
    return result.text.strip()
