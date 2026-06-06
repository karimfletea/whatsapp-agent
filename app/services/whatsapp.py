"""Integración con la WhatsApp Cloud API (Meta): envío y parseo de mensajes."""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("whatsapp")


def _graph_url(phone_number_id: str) -> str:
    return f"https://graph.facebook.com/{settings.whatsapp_api_version}/{phone_number_id}/messages"


def _headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token or settings.whatsapp_token}", "Content-Type": "application/json"}


def send_text(phone_number_id: str, to: str, body: str, token: str | None = None) -> None:
    """Envía un mensaje de texto simple al cliente."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": body[:4096]},
    }
    _post(phone_number_id, payload, token)


def send_menu(phone_number_id: str, to: str, header: str, body: str, rows: list[dict], token: str | None = None) -> None:
    """Envía un menú interactivo (lista) de WhatsApp.

    `rows` = [{"id": "prod_1", "title": "Hamburguesa", "description": "$25.000"}, ...]
    Máximo 10 filas por sección según la API de Meta.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header[:60]},
            "body": {"text": body[:1024]},
            "action": {
                "button": "Ver opciones",
                "sections": [{"title": "Menú", "rows": rows[:10]}],
            },
        },
    }
    _post(phone_number_id, payload, token)


def _post(phone_number_id: str, payload: dict, token: str | None) -> None:
    if not (token or settings.whatsapp_token):
        log.warning("[DEV] Sin WHATSAPP_TOKEN. Mensaje simulado: %s", payload)
        return
    try:
        r = httpx.post(_graph_url(phone_number_id), json=payload, headers=_headers(token), timeout=20)
        if r.status_code >= 400:
            log.error("WhatsApp API %s: %s", r.status_code, r.text)
    except httpx.HTTPError as e:  # no rompemos el flujo si Meta falla
        log.error("Error enviando a WhatsApp: %s", e)


def parse_incoming(payload: dict) -> dict | None:
    """Extrae el primer mensaje de texto entrante de un webhook de Meta.

    Devuelve: {phone_number_id, from, name, text, message_id} o None si no aplica.
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return None  # puede ser un evento de 'statuses' (entregado/leído), lo ignoramos
        msg = value["messages"][0]
        phone_number_id = value["metadata"]["phone_number_id"]
        contact = value.get("contacts", [{}])[0]
        name = contact.get("profile", {}).get("name")

        if msg["type"] == "text":
            text = msg["text"]["body"]
        elif msg["type"] == "interactive":
            inter = msg["interactive"]
            text = inter.get("list_reply", inter.get("button_reply", {})).get("title", "")
        else:
            text = f"[mensaje de tipo {msg['type']} no soportado todavía]"

        return {
            "phone_number_id": phone_number_id,
            "from": msg["from"],
            "name": name,
            "text": text,
            "message_id": msg["id"],
        }
    except (KeyError, IndexError):
        return None
