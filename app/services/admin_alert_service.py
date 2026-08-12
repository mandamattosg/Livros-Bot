from __future__ import annotations

import traceback

import requests

from app.config import settings

ADMIN_ERROR_PREFIX = "🚨 ERRO LIVROS BOT"


def get_admin_chat_id() -> str | None:
    explicit_chat_id = (settings.ADMIN_ALERT_CHAT_ID or "").strip()
    if explicit_chat_id:
        return explicit_chat_id

    fallback_admin_id = (settings.ADMIN_TELEGRAM_ID or "").strip()
    return fallback_admin_id or None


def send_admin_alert(message: str) -> bool:
    if not settings.ADMIN_ALERTS_ENABLED:
        return False

    bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    admin_chat_id = get_admin_chat_id()
    if not bot_token or not admin_chat_id:
        return False

    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": admin_chat_id, "text": message},
            timeout=10,
        )
        return True
    except Exception:
        return False


def send_admin_critical_error_alert(title: str, error: Exception) -> bool:
    formatted = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    message = (
        f"{ADMIN_ERROR_PREFIX}\n\n"
        f"Contexto: {title}\n\n"
        f"{formatted[:3000]}"
    )
    return send_admin_alert(message)
