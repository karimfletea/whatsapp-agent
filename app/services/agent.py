"""Motor de IA: orquesta la conversación con Claude usando tool calling.

Por cada mensaje entrante:
  1. arma el contexto (persona del negocio + historial)
  2. deja que Claude razone y llame herramientas (catálogo, pedido, pago)
  3. devuelve el texto final para enviar por WhatsApp
"""
from __future__ import annotations

import logging

from anthropic import Anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Business, Conversation, Customer, Message
from . import availability as avail_svc
from .tools import TOOLS, dispatch

log = logging.getLogger("agent")
_client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

HISTORY_LIMIT = 20
MAX_TOOL_TURNS = 6


def _system_prompt(business: Business) -> str:
    persona = business.persona or "Eres amable, cercano y resolutivo."
    estado = "ABIERTO" if avail_svc.is_open(business) else "CERRADO"
    return (
        f"Eres el asistente de atención al cliente de '{business.name}', un comercio del tipo "
        f"'{business.vertical}'. Atiendes por WhatsApp, en el idioma del cliente (por defecto español).\n\n"
        f"PERSONALIDAD Y TONO:\n{persona}\n\n"
        f"ESTADO ACTUAL: el comercio está {estado}. {avail_svc.hours_text(business)}\n\n"
        "REGLAS:\n"
        "- Nunca inventes productos, precios ni disponibilidad: usa la herramienta get_catalog.\n"
        "- Para registrar lo que pide el cliente usa create_order; el total lo calcula el sistema.\n"
        "- Antes de cobrar, confirma el pedido y el total con el cliente.\n"
        "- Para cobrar en línea usa generate_payment_link. Si el cliente prefiere transferencia, "
        "Nequi o efectivo, usa register_manual_payment (el comercio verifica el pago después).\n"
        "- Si el cliente quiere hablar con una persona, está molesto, o pide algo que no puedes "
        "resolver, usa request_human_agent.\n"
        "- Si el comercio está cerrado, puedes tomar el pedido igual, pero avísale al cliente que "
        "se atenderá en el horario de atención.\n"
        "- Mensajes cortos y claros, aptos para WhatsApp. Una pregunta a la vez.\n"
        f"- Moneda: {business.currency}."
    )


def _history(db: Session, conversation_id: int) -> list[dict]:
    rows = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc()).limit(HISTORY_LIMIT)
    ).all()
    rows.reverse()
    return [{"role": m.role, "content": m.content} for m in rows]


def generate_reply(db: Session, *, business: Business, customer: Customer,
                   conversation: Conversation, user_text: str) -> str:
    """Genera la respuesta del agente para un mensaje del cliente."""
    if _client is None:
        return ("[Configuración pendiente] Falta ANTHROPIC_API_KEY. "
                "Recibí tu mensaje: " + user_text)

    messages = _history(db, conversation.id)
    messages.append({"role": "user", "content": user_text})

    ctx = dict(db=db, business=business, customer=customer, conversation=conversation)

    for _ in range(MAX_TOOL_TURNS):
        resp = _client.messages.create(
            model=settings.agent_model,
            max_tokens=1024,
            system=_system_prompt(business),
            tools=TOOLS,
            messages=messages,
        )

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    try:
                        result = dispatch(block.name, block.input or {}, **ctx)
                    except Exception as e:  # nunca tumbamos la conversación por un error de tool
                        log.exception("Error en herramienta %s", block.name)
                        result = {"error": str(e)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _json(result),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # Respuesta final (texto).
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    return "Disculpa, tuve un problema procesando tu pedido. ¿Puedes repetirlo, por favor?"


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
