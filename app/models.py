"""Esquema de datos multi-tenant.

Cada `Business` (micro-empresa) es un inquilino aislado: sus productos, clientes,
conversaciones y pedidos viven colgados de su `business_id`. El enrutamiento desde
WhatsApp se hace por `phone_number_id` (el ID del número de WhatsApp en Meta).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    vertical: Mapped[str] = mapped_column(String(60), default="general")  # restaurante, tienda, servicios...
    currency: Mapped[str] = mapped_column(String(3), default="COP")

    # Enrutamiento desde WhatsApp
    phone_number_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    whatsapp_token: Mapped[str | None] = mapped_column(String(512), default=None)  # opcional por-negocio

    # Personalidad del agente para ESTE comercio
    persona: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str | None] = mapped_column(Text, default=None)

    # Pagos
    payment_provider: Mapped[str] = mapped_column(String(40), default="wompi")
    payment_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Atención humana (handoff) y reportes
    staff_wa_id: Mapped[str | None] = mapped_column(String(32), default=None)  # número del dueño/atención

    # Reglas de disponibilidad
    timezone: Mapped[str] = mapped_column(String(40), default="America/Bogota")
    # hours = {"mon": ["09:00", "18:00"], "tue": [...], ...}; día ausente = cerrado
    hours: Mapped[dict] = mapped_column(JSON, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    products: Mapped[list[Product]] = relationship(back_populates="business", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(80), default=None)
    price_cents: Mapped[int] = mapped_column(Integer)  # precio en la moneda menor (centavos)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    stock: Mapped[int | None] = mapped_column(Integer, default=None)  # None = ilimitado
    image_url: Mapped[str | None] = mapped_column(String(512), default=None)

    business: Mapped[Business] = relationship(back_populates="products")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    wa_id: Mapped[str] = mapped_column(String(32), index=True)  # número de teléfono (E.164 sin +)
    name: Mapped[str | None] = mapped_column(String(160), default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed
    mode: Mapped[str] = mapped_column(String(10), default="bot")  # bot | human (handoff)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)

    # draft -> awaiting_payment -> payment_review -> paid -> preparing -> completed | cancelled
    status: Mapped[str] = mapped_column(String(24), default="draft")
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="COP")
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    payment_method: Mapped[str | None] = mapped_column(String(40), default=None)  # online | transferencia | nequi | efectivo
    payment_proof: Mapped[str | None] = mapped_column(Text, default=None)  # referencia o nota del comprobante

    payment_link: Mapped[str | None] = mapped_column(String(512), default=None)
    payment_reference: Mapped[str | None] = mapped_column(String(120), default=None, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    subtotal_cents: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
