"""Configuración central del proyecto, leída desde variables de entorno / .env"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos
    database_url: str = "sqlite:///./dev.db"

    # Motor de IA
    anthropic_api_key: str = ""
    agent_model: str = "claude-sonnet-4-6"

    # WhatsApp Cloud API
    whatsapp_token: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_verify_token: str = "changeme"

    public_base_url: str = "http://localhost:8000"

    # Pasarela de pago (Wompi)
    wompi_base_url: str = "https://sandbox.wompi.co/v1"
    wompi_private_key: str = ""
    wompi_public_key: str = ""


settings = Settings()
