from __future__ import annotations

import logging
import os

import requests

from app.config import settings

ADMIN_ERROR_PREFIX = "🚨 ERRO LIVROS BOT"


class AdminTelegramAlertHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        if not settings.ADMIN_ALERTS_ENABLED:
            return

        bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
        admin_chat_id = (settings.ADMIN_ALERT_CHAT_ID or settings.ADMIN_TELEGRAM_ID or "").strip()
        if not bot_token or not admin_chat_id:
            return

        try:
            message = self.format(record)
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data={"chat_id": admin_chat_id, "text": f"{ADMIN_ERROR_PREFIX}\n\n{message[:3500]}"},
                timeout=8,
            )
        except Exception:
            # Não propaga erro de notificação para o fluxo principal de log.
            return


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger configurado com formato simples e nível definido."""

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        admin_handler = AdminTelegramAlertHandler(level=logging.ERROR)
        admin_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(admin_handler)

    return logging.getLogger(name)
