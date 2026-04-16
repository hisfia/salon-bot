"""
Cliente para la API v2 de Calendly.

Endpoints usados:
  GET  /users/me                         → perfil del usuario
  GET  /event_types                      → servicios del salón
  GET  /event_type_available_times       → horarios libres
  POST /scheduling_links                 → enlace de reserva único
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

import config


class CalendlyError(Exception):
    pass


class CalendlyClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {config.CALENDLY_API_KEY}",
            "Content-Type": "application/json",
        }
        self._base = config.CALENDLY_BASE_URL
        self._user_uri = config.CALENDLY_USER_URI

    # ── helpers ────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        resp = httpx.get(url, headers=self._headers, params=params, timeout=15)
        if resp.status_code != 200:
            raise CalendlyError(f"GET {path} → {resp.status_code}: {resp.text}")
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base}{path}"
        resp = httpx.post(url, headers=self._headers, json=body, timeout=15)
        if resp.status_code not in (200, 201):
            raise CalendlyError(f"POST {path} → {resp.status_code}: {resp.text}")
        return resp.json()

    # ── API pública ────────────────────────────────────────────────────

    def get_event_types(self) -> list[dict[str, Any]]:
        """Devuelve los tipos de evento (servicios) del salón."""
        data = self._get("/event_types", params={"user": self._user_uri, "active": True})
        return [
            {
                "uri": et["uri"],
                "name": et["name"],
                "duration_min": et["duration"],
                "description": et.get("description_plain", ""),
                "scheduling_url": et["scheduling_url"],
            }
            for et in data.get("collection", [])
        ]

    def get_available_slots(
        self,
        event_type_uri: str,
        days_ahead: int = 7,
    ) -> list[dict[str, str]]:
        """
        Retorna los próximos horarios disponibles para un tipo de evento.
        Devuelve hasta 10 slots formateados como strings legibles.
        """
        # +10 min de margen para que Calendly lo acepte como "futuro"
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=10)
        end = start + timedelta(days=days_ahead)

        data = self._get(
            "/event_type_available_times",
            params={
                "event_type": event_type_uri,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
        )

        slots = []
        for item in data.get("collection", [])[:10]:
            dt = datetime.fromisoformat(item["start_time"].replace("Z", "+00:00"))
            # Convertir a hora local del servidor (sin TZ para mostrar limpio)
            local_dt = dt.astimezone()
            slots.append(
                {
                    "start_time": item["start_time"],  # ISO – para crear reserva
                    "display": local_dt.strftime("%A %d/%m/%Y  %H:%M"),
                }
            )
        return slots

    def create_scheduling_link(self, event_type_uri: str) -> str:
        """
        Crea un enlace de reserva de un solo uso.
        Retorna la URL para que el cliente confirme la cita.
        """
        body = {
            "max_event_count": 1,
            "owner": event_type_uri,
            "owner_type": "EventType",
        }
        data = self._post("/scheduling_links", body)
        return data["resource"]["booking_url"]
