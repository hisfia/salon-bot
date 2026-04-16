"""
Síntesis de voz con ElevenLabs.

En TEST_MODE imprime el texto en consola en lugar de reproducir audio.
"""

from __future__ import annotations

import io
import threading

import config

# Importaciones diferidas para no fallar si las libs no están instaladas
# en el primer uso en modo texto.


def speak(text: str) -> None:
    """Convierte texto a voz y lo reproduce. En TEST_MODE solo imprime."""
    if config.TEST_MODE:
        from rich.console import Console
        Console().print(f"\n[bold cyan]🤖 Agente:[/] {text}\n")
        return

    _play_elevenlabs(text)


def _play_elevenlabs(text: str) -> None:
    """Llama a ElevenLabs TTS y reproduce el audio de inmediato."""
    from elevenlabs import ElevenLabs, VoiceSettings
    import sounddevice as sd
    import soundfile as sf

    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    # stream() devuelve un generador de bytes
    audio_stream = client.text_to_speech.convert(
        voice_id=config.ELEVENLABS_VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.3,
            use_speaker_boost=True,
        ),
        output_format="mp3_44100_128",
    )

    # Acumular bytes y reproducir
    audio_bytes = b"".join(audio_stream)
    buf = io.BytesIO(audio_bytes)
    data, samplerate = sf.read(buf, dtype="float32")
    sd.play(data, samplerate)
    sd.wait()
