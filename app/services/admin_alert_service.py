from __future__ import annotations

import logging
import traceback

import requests

from app.config import settings

ADMIN_ERROR_PREFIX = "🚨 ERRO LIVROS BOT"
logger = logging.getLogger(__name__)


def get_admin_chat_id() -> str | None:
    explicit_chat_id = (settings.ADMIN_ALERT_CHAT_ID or "").strip()
    if explicit_chat_id:
        return explicit_chat_id

    fallback_admin_id = (settings.ADMIN_TELEGRAM_ID or "").strip()
    return fallback_admin_id or None


def send_admin_alert(message: str) -> bool:
    if not settings.ADMIN_ALERTS_ENABLED:
        logger.warning("Alerta administrativo não enviado: ADMIN_ALERTS_ENABLED está desativado.")
        return False

    bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    admin_chat_id = get_admin_chat_id()
    if not bot_token:
        logger.warning("Alerta administrativo não enviado: TELEGRAM_BOT_TOKEN não está configurado neste serviço.")
        return False
    if not admin_chat_id:
        logger.warning("Alerta administrativo não enviado: ADMIN_ALERT_CHAT_ID e ADMIN_TELEGRAM_ID estão vazios.")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": admin_chat_id, "text": message},
            timeout=10,
        )
        payload = response.json() if response.content else {}
        if not response.ok or not payload.get("ok", False):
            description = payload.get("description", "Telegram não confirmou o envio")
            logger.warning(
                "Telegram rejeitou o alerta administrativo (HTTP %s): %s",
                response.status_code,
                str(description)[:300],
            )
            return False
        return True
    except requests.RequestException as exc:
        # Do not log exception text: it can contain the Bot API URL and its token.
        logger.warning("Falha de rede ao enviar alerta administrativo (%s).", type(exc).__name__)
        return False
    except (ValueError, TypeError) as exc:
        logger.warning("Resposta inválida do Telegram ao enviar alerta administrativo (%s).", type(exc).__name__)
        return False


def send_admin_critical_error_alert(title: str, error: Exception) -> bool:
    formatted = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    message = (
        f"{ADMIN_ERROR_PREFIX}\n\n"
        f"Contexto: {title}\n\n"
        f"{formatted[:3000]}"
    )
    return send_admin_alert(message)
