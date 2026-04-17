"""
Envío de emails de confirmación de cita al cliente.
Usa Gmail SMTP con contraseña de aplicación.

Para configurarlo:
  1. Activa verificación en 2 pasos en tu cuenta Google
  2. Ve a myaccount.google.com → Seguridad → Contraseñas de aplicaciones
  3. Crea una para "salon-bot" y guárdala en GMAIL_APP_PASSWORD
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_confirmation_email(
    client_name: str,
    client_email: str,
    service: str,
    datetime_str: str,
    salon_name: str = "Salón Belleza Total",
) -> bool:
    """
    Envía un email de confirmación al cliente.
    Devuelve True si se envió correctamente.
    """
    gmail_user = os.getenv("GMAIL_USER", "gestioneshisfia@gmail.com")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")

    if not gmail_pass:
        return False

    subject = f"✅ Confirmación de cita – {salon_name}"

    body_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:500px;margin:auto">
      <h2 style="color:#8B5CF6">¡Tu cita está confirmada! ✂️</h2>
      <p>Hola <strong>{client_name}</strong>,</p>
      <p>Tu cita en <strong>{salon_name}</strong> ha sido confirmada con los siguientes detalles:</p>
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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{salon_name} <{gmail_user}>"
    msg["To"] = client_email
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, client_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[email] Error al enviar: {e}")
        return False
