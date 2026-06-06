"""Conexión a la base de datos y sesión de SQLAlchemy (estilo 2.0)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# check_same_thread solo aplica a SQLite (desarrollo).
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia de FastAPI para inyectar una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
