"""Lógica de pedidos: construir y mantener el pedido borrador de cada conversación."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product


def format_money(cents: int, currency: str = "COP") -> str:
    """Formatea centavos a texto legible. COP no usa decimales en la práctica."""
    if currency.upper() == "COP":
        return f"${cents // 100:,.0f} COP".replace(",", ".")
    return f"{cents / 100:,.2f} {currency.upper()}"


def get_draft_order(db: Session, conversation_id: int) -> Order | None:
    return db.scalar(
        select(Order).where(Order.conversation_id == conversation_id, Order.status == "draft")
    )


def upsert_order(db: Session, *, business_id: int, customer_id: int, conversation_id: int,
                 currency: str, items: list[dict], notes: str | None = None) -> dict:
    """Crea o reemplaza el pedido borrador con los items dados.

    items = [{"product_id": int, "quantity": int}, ...]
    Solo permite productos del MISMO negocio y disponibles (aislamiento multi-tenant).
    """
    order = get_draft_order(db, conversation_id)
    if order is None:
        order = Order(business_id=business_id, customer_id=customer_id,
                      conversation_id=conversation_id, currency=currency, status="draft")
        db.add(order)
        db.flush()
    else:
        order.items.clear()
        db.flush()

    total = 0
    resolved = []
    for raw in items:
        product = db.get(Product, raw["product_id"])
        if not product or product.business_id != business_id or not product.is_available:
            continue  # ignoramos ids inválidos o de otro negocio
        qty = max(1, int(raw.get("quantity", 1)))
        subtotal = product.price_cents * qty
        total += subtotal
        order.items.append(OrderItem(
            product_id=product.id, name=product.name, quantity=qty,
            unit_price_cents=product.price_cents, subtotal_cents=subtotal,
        ))
        resolved.append({"name": product.name, "quantity": qty,
                         "subtotal": format_money(subtotal, currency)})

    order.total_cents = total
    if notes:
        order.notes = notes
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "items": resolved,
        "total_cents": total,
        "total": format_money(total, currency),
        "status": order.status,
    }


# Flujo de estados permitido (máquina de estados simple).
STATUS_FLOW = {
    "draft": {"awaiting_payment", "payment_review", "cancelled"},
    "awaiting_payment": {"payment_review", "paid", "cancelled"},
    "payment_review": {"paid", "cancelled"},          # el staff verifica el comprobante
    "paid": {"preparing", "completed", "cancelled"},
    "preparing": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

STATUS_LABEL = {
    "draft": "Borrador", "awaiting_payment": "Por pagar", "payment_review": "Por verificar",
    "paid": "Pagado", "preparing": "Preparando", "completed": "Completado", "cancelled": "Cancelado",
}


def set_status(db: Session, order: Order, new_status: str) -> dict:
    """Cambia el estado del pedido respetando las transiciones válidas.

    Al pasar a 'paid' descuenta el stock de los productos del pedido.
    """
    if new_status not in STATUS_LABEL:
        return {"error": f"Estado desconocido: {new_status}"}
    if new_status not in STATUS_FLOW.get(order.status, set()):
        return {"error": f"No se puede pasar de '{order.status}' a '{new_status}'."}

    if new_status == "paid":
        from . import availability  # import local para evitar ciclos
        from ..models import Product
        for it in order.items:
            product = db.get(Product, it.product_id)
            if product:
                availability.decrement_stock(product, it.quantity)

    order.status = new_status
    db.commit()
    db.refresh(order)
    return order_summary(db, order)


def order_summary(db: Session, order: Order) -> dict:
    return {
        "order_id": order.id,
        "status": order.status,
        "status_label": STATUS_LABEL.get(order.status, order.status),
        "conversation_id": order.conversation_id,
        "items": [{"name": it.name, "quantity": it.quantity,
                   "subtotal": format_money(it.subtotal_cents, order.currency)} for it in order.items],
        "total": format_money(order.total_cents, order.currency),
        "notes": order.notes,
        "payment_method": order.payment_method,
        "payment_link": order.payment_link,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
