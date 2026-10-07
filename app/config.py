from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL: str | None = os.getenv("DATABASE_URL")


class Settings:
    """Configurações do projeto carregadas a partir de variáveis de ambiente."""

    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Book Price Bot")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    ADMIN_TELEGRAM_ID: str | None = os.getenv("ADMIN_TELEGRAM_ID")
    ADMIN_ALERT_CHAT_ID: str | None = os.getenv("ADMIN_ALERT_CHAT_ID")
    ADMIN_ALERTS_ENABLED: bool = os.getenv("ADMIN_ALERTS_ENABLED", "true").lower() == "true"
    AMAZON_CLIENT_ID: str | None = os.getenv("AMAZON_CLIENT_ID")
    AMAZON_CLIENT_SECRET: str | None = os.getenv("AMAZON_CLIENT_SECRET")
    AMAZON_PARTNER_TAG: str | None = os.getenv("AMAZON_PARTNER_TAG")
    AMAZON_MARKETPLACE: str = os.getenv("AMAZON_MARKETPLACE", "www.amazon.com.br")
    AMAZON_ACCESS_TOKEN: str | None = os.getenv("AMAZON_ACCESS_TOKEN")
    AMAZON_LEGACY_ACCESS_TOKEN: str | None = os.getenv("TOKEN")
    AMAZON_TOKEN_CACHE_FILE: str = os.getenv("AMAZON_TOKEN_CACHE_FILE", str(BASE_DIR / ".amazon_oauth_cache.json"))
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    PRICE_DROP_MINIMUM: Decimal = Decimal(os.getenv("PRICE_DROP_MINIMUM", "4"))
    USER_PRODUCT_MONITOR_LIMIT: int = int(os.getenv("USER_PRODUCT_MONITOR_LIMIT", "10"))
    MONITORING_WORKER_BATCH_SIZE: int = int(os.getenv("MONITORING_WORKER_BATCH_SIZE", "10"))
    MONITORING_WORKER_MAX_RETRIES: int = int(os.getenv("MONITORING_WORKER_MAX_RETRIES", "3"))
    MONITORING_WORKER_POLL_INTERVAL: float = float(os.getenv("MONITORING_WORKER_POLL_INTERVAL", "2.0"))
    MONITORING_WORKER_BATCH_SLEEP: float = float(os.getenv("MONITORING_WORKER_BATCH_SLEEP", "0.5"))
    MONITORING_WORKER_LOCK_TTL: int = int(os.getenv("MONITORING_WORKER_LOCK_TTL", "60"))
    MONITORING_WORKER_STUCK_MINUTES: int = int(os.getenv("MONITORING_WORKER_STUCK_MINUTES", "10"))
    NOTIFICATION_WORKER_BATCH_SIZE: int = int(os.getenv("NOTIFICATION_WORKER_BATCH_SIZE", "20"))
    NOTIFICATION_WORKER_MAX_RETRIES: int = int(os.getenv("NOTIFICATION_WORKER_MAX_RETRIES", "5"))
    NOTIFICATION_WORKER_POLL_INTERVAL: float = float(os.getenv("NOTIFICATION_WORKER_POLL_INTERVAL", "1.5"))
    NOTIFICATION_WORKER_BATCH_SLEEP: float = float(os.getenv("NOTIFICATION_WORKER_BATCH_SLEEP", "0.6"))
    NOTIFICATION_WORKER_LOCK_TTL: int = int(os.getenv("NOTIFICATION_WORKER_LOCK_TTL", "60"))
    NOTIFICATION_WORKER_STUCK_MINUTES: int = int(os.getenv("NOTIFICATION_WORKER_STUCK_MINUTES", "10"))
    REFRESH_HIGH_MONITOR_MIN_USERS: int = int(os.getenv("REFRESH_HIGH_MONITOR_MIN_USERS", "3"))
    REFRESH_HIGH_MONITOR_INTERVAL_HOURS: int = int(os.getenv("REFRESH_HIGH_MONITOR_INTERVAL_HOURS", "6"))
    REFRESH_LOW_MONITOR_INTERVAL_HOURS: int = int(os.getenv("REFRESH_LOW_MONITOR_INTERVAL_HOURS", "12"))
    REFRESH_INTERVAL_TOLERANCE_MINUTES: int = int(os.getenv("REFRESH_INTERVAL_TOLERANCE_MINUTES", "15"))


settings = Settings()
