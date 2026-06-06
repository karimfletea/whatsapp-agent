# Agente de WhatsApp para comercios 🛍️🤖

Plataforma **multi-tenant** para que micro-empresas atiendan, vendan y cobren por WhatsApp
con un agente de IA personalizado por comercio. Construido con **FastAPI + WhatsApp Cloud API
(oficial de Meta) + Claude (tool calling) + Wompi**.

Un solo motor atiende a muchos negocios: cada uno tiene su propio catálogo, tono de voz y
pasarela de pago, y se enruta por el `phone_number_id` de su número de WhatsApp.

## Flujo

```
Cliente (WhatsApp)
   -> WhatsApp Cloud API (Meta)
      -> Webhook (FastAPI)  --enruta por phone_number_id-->  Negocio
         -> Motor IA (Claude + herramientas)
            - get_catalog          (lee el menú real)
            - create_order         (arma el pedido y calcula el total)
            - generate_payment_link(genera el cobro)
            - get_order_status
         -> Responde por WhatsApp
   -> Pasarela (Wompi) --webhook--> marca pagado y avisa al cliente
```

## Estructura

```
app/
  config.py              Variables de entorno
  database.py            Conexión SQLAlchemy
  models.py              Esquema multi-tenant (negocios, productos, pedidos, etc.)
  main.py                App FastAPI + healthcheck + pago simulado (dev)
  seed.py                Datos demo (un restaurante con menú, horarios y stock)
  routers/
    webhook.py           Webhook de WhatsApp + webhook de pagos (respeta handoff)
    admin.py             Alta de negocios/productos, estados, handoff, respuestas, reportes
    dashboard.py         Dashboard visual de pedidos (HTML)
  services/
    whatsapp.py          Enviar/parsear mensajes (Cloud API)
    agent.py             Cerebro: orquesta Claude con tool calling
    tools.py             Herramientas del modelo (catálogo, pedido, pago, disponibilidad, handoff)
    orders.py            Pedidos, totales y máquina de estados
    payments.py          Integración Wompi (+ modo simulado)
    availability.py      Reglas de disponibilidad (horarios + stock)
    reports.py           Reportes diarios
```

## Las 10 prioridades, y dónde viven

1. **Base multi-tenant** — todo cuelga de `business_id` (`models.py`); ruteo por `phone_number_id`.
2. **Dashboard de pedidos** — `routers/dashboard.py`, en `GET /dashboard/{business_id}`.
3. **WhatsApp webhook** — `routers/webhook.py` (`/webhook`).
4. **Motor de conversación** — `services/agent.py` (Claude + herramientas).
5. **Menú/productos** — modelo `Product` + herramienta `get_catalog` + alta en admin.
6. **Estados de pedidos** — máquina de estados en `services/orders.py` (`set_status`), botones en el dashboard.
7. **Human handoff** — herramienta `request_human_agent`; el bot se pausa (`Conversation.mode='human'`) y el staff responde desde el dashboard.
8. **Pago por verificar** — herramienta `register_manual_payment` deja el pedido "Por verificar"; el staff lo aprueba.
9. **Reglas de disponibilidad** — `services/availability.py` (horarios + stock).
10. **Reportes diarios** — `services/reports.py` (`GET /admin/businesses/{id}/report`).

## El dashboard

Con el servidor corriendo y la demo cargada, abre en el navegador:

```
http://localhost:8000/dashboard/1
```

Verás el tablero de pedidos por estado (Borrador → Por pagar → Por verificar → Pagado → Preparando → Completado), los indicadores del día (pedidos, ingresos, ticket promedio) y el panel de atención humana para responder a clientes que pidieron hablar con una persona. Se actualiza solo cada 8 segundos.

## Puesta en marcha (desarrollo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edita tus llaves
python -m app.seed            # crea el negocio demo
uvicorn app.main:app --reload
```

Sin `ANTHROPIC_API_KEY` el agente responde con un stub (útil para probar la mensajería).
Sin `WOMPI_PRIVATE_KEY` los pagos usan una página simulada en `/pay/mock/...`.

### Conectar WhatsApp (Cloud API)

1. Crea una app en Meta for Developers y añade el producto WhatsApp.
2. Expón tu backend con una URL pública (en dev: `ngrok http 8000`).
3. En la consola de Meta configura el webhook con:
   - URL: `https://TU-DOMINIO/webhook`
   - Verify token: el valor de `WHATSAPP_VERIFY_TOKEN`
   - Suscríbete al campo `messages`.
4. Pon el `phone_number_id` de tu número en el negocio (campo `phone_number_id`).

## Probar el flujo completo

1. Da de alta un negocio y su catálogo vía la API admin (`POST /admin/businesses`, `POST /admin/businesses/{id}/products`) o usa la demo.
2. Escribe al número desde WhatsApp: el agente saluda, muestra el menú, arma el pedido y manda el link de pago.
3. Al pagar (o "pagar" en la página simulada), el webhook marca el pedido como `paid` y avisa al cliente.

## Próximos pasos sugeridos

- **Autenticación** en la API admin (JWT) y panel web para el negocio.
- **Migraciones** con Alembic (hoy se crean las tablas automáticamente).
- **Multi-tenant real**: onboarding con Meta Embedded Signup para que cada negocio
  conecte su propio número y token sin intervención manual.
- **Mensajes interactivos**: usar `send_menu` (listas/botones) para el catálogo.
- **Cola de trabajos** (Celery/Redis o RQ) en vez de BackgroundTasks para escalar.
- **Verificación de firma** real del webhook de Wompi en `payments.verify_event`.
- **Métricas**: pedidos por negocio, tasa de conversión, ticket promedio.
```
```
