"""
Envío de emails de confirmación usando Resend (API HTTP, sin SMTP).
Railway bloquea SMTP saliente, pero las llamadas HTTP funcionan perfectamente.

Para configurarlo:
  1. Crea cuenta gratis en resend.com (3.000 emails/mes)
  2. Ve a API Keys → Create API Key
  3. Guarda la clave en RESEND_API_KEY
"""

from __future__ import annotations

import os
import httpx


def send_confirmation_email(
    client_name: str,
    client_email: str,
    service: str,
    datetime_str: str,
    salon_name: str = "Salón Belleza Total",
) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        print("[email] RESEND_API_KEY no configurada")
        return False

    from_email = os.getenv("RESEND_FROM_EMAIL", f"citas@{salon_name.lower().replace(' ','-')}.com")

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:500px;margin:auto">
      <h2 style="color:#8B5CF6">¡Tu cita está confirmada! ✂️</h2>
      <p>Hola <strong>{client_name}</strong>,</p>
      <p>Tu cita en <strong>{salon_name}</strong> ha sido confirmada:</p>
      <table style="border-collapse:collapse;width:100%;margin:20px 0">
        <tr style="background:#f9f5ff">
          <td style="padding:10px;border:1px solid #ddd"><strong>Servicio</strong></td>
          <td style="padding:10px;border:1px solid #ddd">{service}</td>
        </tr>
        <tr>
          <td style="padding:10px;border:1px solid #ddd"><strong>Fecha y hora</strong></td>
          <td style="padding:10px;border:1px solid #ddd">{datetime_str}</td>
        </tr>
      </table>
      <p>Si necesitas modificar o cancelar tu cita, contáctanos con antelación.</p>
      <p style="color:#888;font-size:12px">— {salon_name}</p>
    </body></html>
    """

    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": f"{salon_name} <{from_email}>",
                "to": [client_email],
                "subject": f"✅ Confirmación de cita – {salon_name}",
                "html": html,
            },
            timeout=15,
        )
        if r.status_code in (200, 201):
            return True
        print(f"[email] Resend error {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"[email] Error: {e}")
        return False
