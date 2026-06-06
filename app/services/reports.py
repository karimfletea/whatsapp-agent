"""Reportes diarios por negocio: pedidos, ingresos, ticket promedio y top de productos."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Business, Order, OrderItem
from .orders import format_money

PAID_STATES = {"paid", "preparing", "completed"}


def daily_report(db: Session, business: Business, day: dt.date | None = None) -> dict:
    """Calcula el reporte de un día (por defecto hoy, en la zona horaria del negocio)."""
    tz = ZoneInfo(business.timezone or "America/Bogota")
    day = day or dt.datetime.now(tz).date()
    # Ventana del día en hora local, convertida a UTC para comparar contra lo almacenado.
    start = dt.datetime.combine(day, dt.time.min, tzinfo=tz).astimezone(dt.timezone.utc)
    end = start + dt.timedelta(days=1)

    orders = db.scalars(
        select(Order).where(
            Order.business_id == business.id,
            Order.created_at >= start,
            Order.created_at < end,
        )
    ).all()

    by_status: Counter = Counter(o.status for o in orders)
    paid = [o for o in orders if o.status in PAID_STATES]
    revenue = sum(o.total_cents for o in paid)
    avg_ticket = revenue // len(paid) if paid else 0

    # Top productos por cantidad (solo de pedidos pagados)
    items: Counter = Counter()
    if paid:
        rows = db.scalars(
            select(OrderItem).where(OrderItem.order_id.in_([o.id for o in paid]))
        ).all()
        for it in rows:
            items[it.name] += it.quantity

    return {
        "business": business.name,
        "date": day.isoformat(),
        "orders_total": len(orders),
        "orders_paid": len(paid),
        "revenue_cents": revenue,
        "revenue": format_money(revenue, business.currency),
        "avg_ticket": format_money(avg_ticket, business.currency),
        "by_status": dict(by_status),
        "top_products": [{"name": n, "quantity": q} for n, q in items.most_common(5)],
    }


def report_text(report: dict) -> str:
    """Versión en texto del reporte, lista para enviar por WhatsApp al dueño."""
    top = "\n".join(f"  • {p['name']} ×{p['quantity']}" for p in report["top_products"]) or "  (sin ventas)"
    return (
        f"📊 Reporte de {report['business']} — {report['date']}\n"
        f"Pedidos: {report['orders_total']} (pagados: {report['orders_paid']})\n"
        f"Ingresos: {report['revenue']}\n"
        f"Ticket promedio: {report['avg_ticket']}\n"
        f"Top productos:\n{top}"
    )
