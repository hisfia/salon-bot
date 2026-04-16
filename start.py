"""
Arranca el servidor webhook, crea el túnel SSH (localhost.run) y actualiza
el agente en ElevenLabs con webhook tools — todo en un solo comando.

Uso:
    python start.py

Ctrl+C para detener.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time

import uvicorn
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()
PORT = 8000


# ── Servidor FastAPI ───────────────────────────────────────────────────────────

def start_server() -> None:
    from webhook_server import app
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


def wait_for_server(timeout: int = 10) -> bool:
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(f"http://localhost:{PORT}/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# ── Túnel SSH con localhost.run ────────────────────────────────────────────────

def open_tunnel() -> str:
    """
    Abre un túnel SSH a localhost.run y devuelve la URL pública.
    Sin registro, sin cuenta — solo SSH.
    """
    proc = subprocess.Popen(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-R", f"80:localhost:{PORT}",
            "nokey@localhost.run",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # localhost.run imprime la URL en los primeros segundos
    deadline = time.time() + 20
    while time.time() < deadline:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if not line:
            break
        # Buscar URL en la salida: https://xxxx.lhr.life
        match = re.search(r"https://[a-zA-Z0-9\-]+\.lhr\.life", line)
        if match:
            return match.group(0), proc  # type: ignore[return-value]

    proc.kill()
    raise RuntimeError("No se pudo obtener la URL del túnel.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:

    # 1. Servidor FastAPI
    console.rule("[bold]Paso 1 – Servidor webhook[/]")
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not wait_for_server():
        console.print("[red]✗ El servidor no arrancó a tiempo.[/]")
        sys.exit(1)
    console.print(f"[green]✓ Servidor corriendo en http://localhost:{PORT}[/]")

    # 2. Túnel SSH
    console.rule("[bold]Paso 2 – Túnel público (localhost.run)[/]")
    console.print("[dim]Abriendo túnel SSH…[/]")
    try:
        public_url, tunnel_proc = open_tunnel()
        console.print(f"[green]✓ URL pública:[/] [bold]{public_url}[/]")
    except Exception as e:
        console.print(f"[red]✗ Error al abrir túnel: {e}[/]")
        sys.exit(1)

    # 3. Actualizar agente ElevenLabs
    console.rule("[bold]Paso 3 – Actualizar agente ElevenLabs[/]")
    result = subprocess.run(
        [sys.executable, "setup_agent.py", "--webhook", public_url],
        capture_output=False,
    )
    if result.returncode != 0:
        console.print("[red]✗ Error al actualizar el agente.[/]")
        tunnel_proc.kill()
        sys.exit(1)

    # 4. Listo
    console.rule("[bold green]¡Listo![/]")
    console.print(
        f"\n  El agente [bold]Valeria[/] ya usa webhooks en tiempo real.\n"
        f"  Abre [bold]elevenlabs.io[/] → tu agente → [bold]Talk[/] y pide una cita.\n"
        f"\n  [dim]Ctrl+C para detener (el agente dejará de responder herramientas).[/dim]\n"
    )

    try:
        while True:
            time.sleep(1)
            if tunnel_proc.poll() is not None:
                console.print("[yellow]Túnel desconectado. Reinicia con: python start.py[/]")
                break
    except KeyboardInterrupt:
        console.print("\n[yellow]Servidor detenido.[/]")
        tunnel_proc.kill()


if __name__ == "__main__":
    main()
