"""API de administración (base del panel del negocio).

CRUD mínimo para dar de alta comercios y su catálogo, y ver pedidos. En producción
protégelo con autenticación (JWT/OAuth) y filtra siempre por el negocio del usuario.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Business, Conversation, Customer, Message, Order, Product
from ..services import reports as reports_svc
from ..services import whatsapp as wa_svc
from ..services.orders import order_summary, set_status

router = APIRouter(prefix="/admin", tags=["admin"])


class BusinessIn(BaseModel):
    name: str
    vertical: str = "general"
    currency: str = "COP"
    phone_number_id: str
    persona: str = ""
    whatsapp_token: str | None = None


class ProductIn(BaseModel):
    name: str
    price_cents: int
    description: str | None = None
    category: str | None = None
    image_url: str | None = None


@router.post("/businesses")
def create_business(data: BusinessIn, db: Session = Depends(get_db)):
    if db.scalar(select(Business).where(Business.phone_number_id == data.phone_number_id)):
        raise HTTPException(409, "Ya existe un negocio con ese phone_number_id")
    biz = Business(**data.model_dump())
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return {"id": biz.id, "name": biz.name}


@router.post("/businesses/{business_id}/products")
def add_product(business_id: int, data: ProductIn, db: Session = Depends(get_db)):
    if not db.get(Business, business_id):
        raise HTTPException(404, "Negocio no encontrado")
    product = Product(business_id=business_id, **data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "name": product.name}


@router.get("/businesses/{business_id}/orders")
def list_orders(business_id: int, db: Session = Depends(get_db)):
    orders = db.scalars(
        select(Order).where(Order.business_id == business_id).order_by(Order.created_at.desc())
    ).all()
    return [order_summary(db, o) | {"customer_id": o.customer_id} for o in orders]


def _customer_name(db: Session, customer_id: int) -> str:
    c = db.get(Customer, customer_id)
    return (c.name or c.wa_id) if c else "Cliente"


@router.get("/businesses/{business_id}/board")
def board(business_id: int, db: Session = Depends(get_db)):
    """Datos del dashboard: pedidos (excepto borradores vacíos) + conversaciones en modo humano."""
    orders = db.scalars(
        select(Order).where(Order.business_id == business_id).order_by(Order.created_at.desc())
    ).all()
    order_rows = [
        order_summary(db, o) | {"customer": _customer_name(db, o.customer_id)}
        for o in orders if o.items
    ]

    convos = db.scalars(
        select(Conversation).where(
            Conversation.business_id == business_id, Conversation.mode == "human"
        )
    ).all()
    handoffs = []
    for c in convos:
        last = db.scalar(
            select(Message).where(Message.conversation_id == c.id)
            .order_by(Message.created_at.desc()).limit(1)
        )
        handoffs.append({
            "conversation_id": c.id,
            "customer": _customer_name(db, c.customer_id),
            "last_message": last.content if last else "",
        })
    return {"orders": order_rows, "handoffs": handoffs}


class StatusIn(BaseModel):
    status: str


@router.patch("/orders/{order_id}")
def update_order_status(order_id: int, data: StatusIn, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    result = set_status(db, order, data.status)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


class HandoffIn(BaseModel):
    action: str  # take | release


@router.post("/conversations/{conversation_id}/handoff")
def handoff(conversation_id: int, data: HandoffIn, db: Session = Depends(get_db)):
    convo = db.get(Conversation, conversation_id)
    if not convo:
        raise HTTPException(404, "Conversación no encontrada")
    convo.mode = "human" if data.action == "take" else "bot"
    db.commit()
    return {"conversation_id": convo.id, "mode": convo.mode}


class ReplyIn(BaseModel):
    text: str


@router.post("/conversations/{conversation_id}/reply")
def staff_reply(conversation_id: int, data: ReplyIn, db: Session = Depends(get_db)):
    """Un humano responde al cliente por WhatsApp desde el dashboard."""
    convo = db.get(Conversation, conversation_id)
    if not convo:
        raise HTTPException(404, "Conversación no encontrada")
    business = db.get(Business, convo.business_id)
    customer = db.get(Customer, convo.customer_id)
    db.add(Message(conversation_id=convo.id, role="assistant", content=data.text))
    db.commit()
    token = business.whatsapp_token or settings.whatsapp_token
    wa_svc.send_text(business.phone_number_id, customer.wa_id, data.text, token=token)
    return {"ok": True}


@router.get("/businesses/{business_id}/report")
def daily_report(business_id: int, db: Session = Depends(get_db)):
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(404, "Negocio no encontrado")
    return reports_svc.daily_report(db, business)
