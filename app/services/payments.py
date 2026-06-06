"""Pasarela de pago. Implementación de referencia: Wompi (Colombia).

En desarrollo (sin llaves) genera un link simulado para poder probar el flujo
completo end-to-end sin credenciales reales.
"""
from __future__ import annotations

import logging
import uuid

import httpx

from ..config import settings
from ..models import Order

log = logging.getLogger("payments")


def create_payment_link(order: Order) -> dict:
    """Crea un link de cobro para el pedido y devuelve {url, reference}."""
    reference = f"ORD-{order.id}-{uuid.uuid4().hex[:8]}"

    if not settings.wompi_private_key:
        # Modo desarrollo: link simulado.
        url = f"{settings.public_base_url}/pay/mock/{reference}"
        log.warning("[DEV] Pago simulado para %s -> %s", reference, url)
        return {"url": url, "reference": reference, "provider": "mock"}

    # Wompi: Payment Links API.
    payload = {
        "name": f"Pedido #{order.id}",
        "description": f"Pago del pedido #{order.id}",
        "single_use": True,
        "collect_shipping": False,
        "currency": order.currency,
        "amount_in_cents": order.total_cents,
        "redirect_url": f"{settings.public_base_url}/pay/return?ref={reference}",
        "reference": reference,
    }
    try:
        r = httpx.post(
            f"{settings.wompi_base_url}/payment_links",
            json=payload,
            headers={"Authorization": f"Bearer {settings.wompi_private_key}"},
            timeout=20,
        )
        r.raise_for_status()
        link_id = r.json()["data"]["id"]
        return {"url": f"https://checkout.wompi.co/l/{link_id}", "reference": reference, "provider": "wompi"}
    except httpx.HTTPError as e:
        log.error("Error creando link Wompi: %s", e)
        return {"url": None, "reference": reference, "provider": "wompi", "error": str(e)}


def verify_event(headers: dict, body: dict) -> bool:
    """Punto de extensión: validar la firma del webhook de Wompi (events).

    Wompi firma con SHA256 sobre propiedades + secreto de eventos. Aquí se deja
    el gancho; en producción DEBES validar antes de marcar como pagado.
    """
    return True  # TODO: implementar verificación real de firma
