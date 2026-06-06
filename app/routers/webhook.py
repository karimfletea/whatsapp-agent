"""Endpoints del webhook de WhatsApp y de confirmación de pagos."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response
from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import Business, Conversation, Customer, Message, Order
from ..services import agent, orders as orders_svc, payments, whatsapp

log = logging.getLogger("webhook")
router = APIRouter()


@router.get("/webhook")
def verify(request: Request):
    """Verificación del webhook que exige Meta al configurarlo (handshake)."""
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == settings.whatsapp_verify_token:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook")
async def receive(request: Request, background: BackgroundTasks):
    """Recibe eventos de WhatsApp. Respondemos 200 de inmediato y procesamos aparte
    (Meta reintenta si tardamos; el LLM puede tomar segundos)."""
    payload = await request.json()
    incoming = whatsapp.parse_incoming(payload)
    if incoming:
        background.add_task(_process_message, incoming)
    return {"status": "ok"}


def _process_message(incoming: dict) -> None:
    """Procesa un mensaje entrante: enruta al negocio, corre el agente y responde."""
    db = SessionLocal()
    try:
        business = db.scalar(
            select(Business).where(
                Business.phone_number_id == incoming["phone_number_id"],
                Business.is_active.is_(True),
            )
        )
        if not business:
            log.warning("Sin negocio para phone_number_id=%s", incoming["phone_number_id"])
            return

        customer = db.scalar(
            select(Customer).where(Customer.business_id == business.id, Customer.wa_id == incoming["from"])
        )
        if not customer:
            customer = Customer(business_id=business.id, wa_id=incoming["from"], name=incoming.get("name"))
            db.add(customer)
            db.commit()
            db.refresh(customer)

        conversation = db.scalar(
            select(Conversation).where(
                Conversation.business_id == business.id,
                Conversation.customer_id == customer.id,
                Conversation.status == "open",
            )
        )
        if not conversation:
            conversation = Conversation(business_id=business.id, customer_id=customer.id)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

        db.add(Message(conversation_id=conversation.id, role="user", content=incoming["text"]))
        db.commit()

        # Handoff: si una persona tomó la conversación, el bot NO responde.
        if conversation.mode == "human":
            if business.staff_wa_id:
                token = business.whatsapp_token or settings.whatsapp_token
                whatsapp.send_text(business.phone_number_id, business.staff_wa_id,
                                   f"💬 {customer.name or customer.wa_id}: {incoming['text']}", token=token)
            return

        reply = agent.generate_reply(
            db, business=business, customer=customer, conversation=conversation, user_text=incoming["text"]
        )

        db.add(Message(conversation_id=conversation.id, role="assistant", content=reply))
        db.commit()

        token = business.whatsapp_token or settings.whatsapp_token
        whatsapp.send_text(business.phone_number_id, incoming["from"], reply, token=token)
    except Exception:
        log.exception("Error procesando mensaje")
    finally:
        db.close()


@router.post("/payments/webhook")
async def payment_webhook(request: Request):
    """Confirmación de pago de la pasarela (Wompi). Marca el pedido como pagado
    y avisa al cliente por WhatsApp."""
    body = await request.json()
    if not payments.verify_event(dict(request.headers), body):
        return Response(status_code=403)

    # Estructura típica de Wompi: body["data"]["transaction"] con reference y status.
    tx = body.get("data", {}).get("transaction", {})
    reference = tx.get("reference")
    status = tx.get("status")
    if not reference:
        return {"status": "ignored"}

    db = SessionLocal()
    try:
        order = db.scalar(select(Order).where(Order.payment_reference == reference))
        if order and status == "APPROVED" and order.status in ("awaiting_payment", "payment_review"):
            orders_svc.set_status(db, order, "paid")
            business = db.get(Business, order.business_id)
            customer = db.get(Customer, order.customer_id)
            if business and customer:
                token = business.whatsapp_token or settings.whatsapp_token
                whatsapp.send_text(
                    business.phone_number_id, customer.wa_id,
                    f"¡Pago confirmado! Tu pedido #{order.id} ya está en preparación. 🙌",
                    token=token,
                )
        return {"status": "ok"}
    finally:
        db.close()
