"""Reglas de disponibilidad: horario de atención del negocio y stock de productos."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ..models import Business, Product

_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY_ES = {"mon": "lun", "tue": "mar", "wed": "mié", "thu": "jue",
           "fri": "vie", "sat": "sáb", "sun": "dom"}


def _now(business: Business) -> dt.datetime:
    try:
        return dt.datetime.now(ZoneInfo(business.timezone or "America/Bogota"))
    except Exception:
        return dt.datetime.now(ZoneInfo("America/Bogota"))


def is_open(business: Business, now: dt.datetime | None = None) -> bool:
    """¿El negocio está abierto ahora según sus horarios? Sin horarios definidos = siempre abierto."""
    hours = business.hours or {}
    if not hours:
        return True
    now = now or _now(business)
    rng = hours.get(_DAYS[now.weekday()])
    if not rng or len(rng) != 2:
        return False  # día sin horario = cerrado
    try:
        open_t = dt.time.fromisoformat(rng[0])
        close_t = dt.time.fromisoformat(rng[1])
    except ValueError:
        return True
    return open_t <= now.time() <= close_t


def hours_text(business: Business) -> str:
    """Resumen legible de los horarios, para que el agente lo comunique."""
    hours = business.hours or {}
    if not hours:
        return "Atendemos en cualquier momento."
    partes = [f"{_DAY_ES[d]} {r[0]}-{r[1]}" for d in _DAYS if (r := hours.get(d)) and len(r) == 2]
    return "Horario: " + ", ".join(partes) if partes else "Horario no definido."


def product_available(product: Product) -> bool:
    """Un producto está disponible si está marcado disponible y tiene stock (o stock ilimitado)."""
    if not product.is_available:
        return False
    return product.stock is None or product.stock > 0


def decrement_stock(product: Product, quantity: int) -> None:
    """Descuenta stock si el producto lo controla (se llama al confirmar el pago)."""
    if product.stock is not None:
        product.stock = max(0, product.stock - quantity)
