"""Herramientas que el motor de IA puede llamar (tool use de Claude).

El modelo NO inventa precios ni pedidos: para todo lo que toca datos del negocio
llama a estas funciones, que leen/escriben en la base de datos del inquilino.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Business, Conversation, Customer, Order, Product
from . import availability as avail_svc
from . import orders as orders_svc
from . import payments as payments_svc
from . import whatsapp as wa_svc

# Esquemas de herramientas en el formato de la Messages API de Anthropic.
TOOLS = [
    {
        "name": "get_catalog",
        "description": "Devuelve los productos disponibles del comercio (con precios reales). "
                       "Úsala cuando el cliente pida el menú, la carta, el catálogo o pregunte qué hay.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filtrar por categoría (opcional)."}
            },
        },
    },
    {
        "name": "create_order",
        "description": "Crea o actualiza el pedido del cliente con la lista de items. "
                       "Calcula el total automáticamente. Llámala cuando el cliente confirme qué quiere.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "integer"},
                        },
                        "required": ["product_id", "quantity"],
                    },
                },
                "notes": {"type": "string", "description": "Notas del pedido (sin cebolla, para llevar, etc.)."},
            },
            "required": ["items"],
        },
    },
    {
        "name": "generate_payment_link",
        "description": "Genera el link de pago para el pedido actual. Úsala SOLO después de que "
                       "el cliente confirme el pedido y el total. Devuelve la URL para cobrar.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_order_status",
        "description": "Consulta el estado y contenido del pedido actual del cliente.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_availability",
        "description": "Indica si el comercio está abierto ahora y su horario de atención. "
                       "Úsala si el cliente pregunta si están abiertos o a qué hora atienden.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "register_manual_payment",
        "description": "Registra que el cliente pagará por un medio que requiere verificación humana "
                       "(transferencia, Nequi, efectivo). Deja el pedido 'por verificar' y avisa al comercio. "
                       "Úsala cuando el cliente NO quiera pagar con el link en línea.",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "transferencia | nequi | efectivo"},
                "proof": {"type": "string", "description": "Referencia o nota del comprobante (opcional)."},
            },
            "required": ["method"],
        },
    },
    {
        "name": "request_human_agent",
        "description": "Transfiere la conversación a una persona del comercio y pausa al asistente. "
                       "Úsala cuando el cliente lo pida explícitamente, esté molesto, o sea algo que no puedes resolver.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Motivo breve de la transferencia."}
            },
        },
    },
]


def dispatch(name: str, tool_input: dict, *, db: Session, business: Business,
             customer: Customer, conversation: Conversation) -> dict:
    """Ejecuta la herramienta solicitada por el modelo y devuelve un dict (resultado)."""
    if name == "get_catalog":
        stmt = select(Product).where(Product.business_id == business.id, Product.is_available.is_(True))
        if tool_input.get("category"):
            stmt = stmt.where(Product.category == tool_input["category"])
        products = [p for p in db.scalars(stmt).all() if avail_svc.product_available(p)]
        return {
            "open_now": avail_svc.is_open(business),
            "products": [
                {
                    "product_id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "category": p.category,
                    "price": orders_svc.format_money(p.price_cents, business.currency),
                }
                for p in products
            ],
        }

    if name == "create_order":
        return orders_svc.upsert_order(
            db,
            business_id=business.id,
            customer_id=customer.id,
            conversation_id=conversation.id,
            currency=business.currency,
            items=tool_input.get("items", []),
            notes=tool_input.get("notes"),
        )

    if name == "generate_payment_link":
        order = orders_svc.get_draft_order(db, conversation.id)
        if not order or not order.items:
            return {"error": "No hay un pedido para cobrar. Crea el pedido primero."}
        result = payments_svc.create_payment_link(order)
        if result.get("url"):
            order.payment_link = result["url"]
            order.payment_reference = result["reference"]
            order.status = "awaiting_payment"
            db.commit()
        return result

    if name == "get_order_status":
        order = db.scalar(
            select(Order).where(Order.conversation_id == conversation.id)
            .order_by(Order.created_at.desc())
        )
        if not order:
            return {"status": "sin_pedido", "message": "El cliente aún no tiene pedido."}
        return orders_svc.order_summary(db, order)

    if name == "check_availability":
        return {"open_now": avail_svc.is_open(business), "hours": avail_svc.hours_text(business)}

    if name == "register_manual_payment":
        order = orders_svc.get_draft_order(db, conversation.id)
        if not order or not order.items:
            return {"error": "No hay un pedido para registrar el pago. Crea el pedido primero."}
        order.payment_method = tool_input.get("method", "transferencia")
        order.payment_proof = tool_input.get("proof")
        orders_svc.set_status(db, order, "payment_review")
        _notify_staff(db, business,
                      f"🧾 Pedido #{order.id} POR VERIFICAR ({order.payment_method}). "
                      f"Total {orders_svc.format_money(order.total_cents, business.currency)}. "
                      f"Revísalo en el dashboard.")
        return {"ok": True, "status": "payment_review",
                "message": "Pago registrado. El comercio lo verifica y confirma tu pedido enseguida."}

    if name == "request_human_agent":
        conversation.mode = "human"
        db.commit()
        _notify_staff(db, business,
                      f"🙋 El cliente {customer.wa_id} pidió hablar con una persona. "
                      f"Motivo: {tool_input.get('reason', 'no especificado')}. Responde desde el dashboard.")
        return {"ok": True, "message": "Te paso con una persona del equipo; en breve te responden."}

    return {"error": f"Herramienta desconocida: {name}"}


def _notify_staff(db: Session, business: Business, message: str) -> None:
    """Avisa por WhatsApp al dueño/atención del comercio (si configuró su número)."""
    if business.staff_wa_id:
        token = business.whatsapp_token or settings.whatsapp_token
        wa_svc.send_text(business.phone_number_id, business.staff_wa_id, message, token=token)
