"""Carga un comercio de demostración (restaurante) con su menú.

Uso:  python -m app.seed
"""
from __future__ import annotations

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import Business, Product

Base.metadata.create_all(bind=engine)


def run() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(Business).where(Business.phone_number_id == "DEMO_PHONE_ID")):
            print("La demo ya existe.")
            return

        biz = Business(
            name="Burger House",
            vertical="restaurante",
            currency="COP",
            phone_number_id="DEMO_PHONE_ID",  # reemplaza por tu phone_number_id real de Meta
            staff_wa_id=None,                  # pon aquí el WhatsApp del dueño para recibir avisos
            timezone="America/Bogota",
            hours={  # día ausente = cerrado
                "mon": ["11:00", "22:00"], "tue": ["11:00", "22:00"], "wed": ["11:00", "22:00"],
                "thu": ["11:00", "22:00"], "fri": ["11:00", "23:00"], "sat": ["12:00", "23:00"],
            },
            persona=("Cercano, con buena energía y rápido. Usa un emoji de vez en cuando 🍔. "
                     "Recomienda combos cuando tenga sentido."),
        )
        db.add(biz)
        db.flush()

        # (nombre, descripción, categoría, precio_centavos, stock)
        menu = [
            ("Hamburguesa clásica", "Carne, queso, lechuga y tomate", "Hamburguesas", 2500000, None),
            ("Hamburguesa doble", "Doble carne y doble queso", "Hamburguesas", 3500000, 20),
            ("Papas fritas", "Porción grande crocante", "Acompañamientos", 1200000, None),
            ("Gaseosa", "350 ml", "Bebidas", 600000, 50),
            ("Combo clásico", "Hamburguesa clásica + papas + gaseosa", "Combos", 3800000, None),
        ]
        for name, desc, cat, cents, stock in menu:
            db.add(Product(business_id=biz.id, name=name, description=desc, category=cat,
                           price_cents=cents, stock=stock))

        db.commit()
        print(f"Demo creada: negocio #{biz.id} con {len(menu)} productos.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
