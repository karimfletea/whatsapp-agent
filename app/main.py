"""Aplicación FastAPI: punto de entrada."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .database import Base, engine
from .routers import admin, dashboard, webhook

logging.basicConfig(level=logging.INFO)

# Crea las tablas si no existen (en producción usa Alembic para migraciones).
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agente WhatsApp para comercios", version="0.1.0")
app.include_router(webhook.router, tags=["whatsapp"])
app.include_router(admin.router)
app.include_router(dashboard.router, tags=["dashboard"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/pay/mock/{reference}", response_class=HTMLResponse)
def mock_pay(reference: str):
    """Página de pago simulada para desarrollo (sin Wompi).

    Al 'pagar', dispara el webhook de pago como lo haría la pasarela real.
    """
    return f"""
    <html><body style="font-family:sans-serif;text-align:center;padding:60px">
      <h2>Pago simulado</h2>
      <p>Referencia: <code>{reference}</code></p>
      <button onclick="pay()" style="padding:12px 24px;font-size:16px">Pagar ahora</button>
      <p id="msg"></p>
      <script>
        async function pay() {{
          await fetch('/payments/webhook', {{
            method:'POST', headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({{data:{{transaction:{{reference:'{reference}',status:'APPROVED'}}}}}})
          }});
          document.getElementById('msg').textContent = '¡Pago aprobado! Revisa tu WhatsApp.';
        }}
      </script>
    </body></html>
    """
