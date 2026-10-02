from __future__ import annotations

import json
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.logging import get_logger
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.utils.affiliate_link import build_affiliate_link

logger = get_logger("app.services.notification_service")


class NotificationService:
    """Serviço responsável por enviar notificações de queda de preço aos usuários."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _normalize_chat_id(self, telegram_id: str | int | None) -> str | int | None:
        if telegram_id is None:
            return None
        if isinstance(telegram_id, int):
            return telegram_id
        value = str(telegram_id).strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value

    def _build_offer_link(self, product: Product) -> str:
        return build_affiliate_link(
            product.affiliate_link,
            product.asin,
            settings.AMAZON_PARTNER_TAG,
            fallback_to_product_url=True,
        ) or "https://www.amazon.com.br"

    def _send_message(self, chat_id: str | int, message: str, product: Product | None = None) -> None:
        if not settings.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        if product is not None:
            offer_link = self._build_offer_link(product)
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [[{"text": "📲 Ver oferta na Amazon", "url": offer_link, "style": "primary"}]]
            })

        try:
            response = requests.post(url, data=payload, timeout=10)
            payload_response = response.json() if response.content else {}
            if not payload_response.get("ok", False):
                description = payload_response.get("description", "Erro desconhecido ao enviar mensagem")
                raise RuntimeError(description)
        except (ConnectionError, TimeoutError, requests.exceptions.RequestException) as exc:
            # Erros de rede: registra mas não quebra o fluxo
            logger.warning("Erro temporário de rede ao enviar mensagem: %s", exc)
            raise RuntimeError(f"Erro temporário de rede: {exc}") from exc

    def send_drop_notification(self, drop_event: dict, product: Product) -> int:
        """Envia uma notificação para todos os usuários associados ao produto."""

        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN não configurado; notificação não enviada.")
            return 0

        relations = self.db.query(UserProduct).filter(UserProduct.product_id == product.id).all()
        sent = 0
        for relation in relations:
            user = self.db.query(User).filter(User.id == relation.user_id).first()
            if not user or not getattr(user, "is_active", True):
                continue

            chat_id = self._normalize_chat_id(user.telegram_id)
            if chat_id is None:
                logger.warning("Usuário %s não possui um chat do Telegram registrado; notificação não enviada.", user.id)
                continue

            message = self._build_message(product, drop_event)
            try:
                self._send_message(chat_id, message, product)
                sent += 1
                logger.info("Notificação enviada para o usuário %s", chat_id)
            except RuntimeError as exc:
                reason = str(exc)
                # Erros de rede: registra mas continua tentando outros usuários
                if "Erro temporário de rede" in reason:
                    logger.warning("Falha temporária de rede ao enviar para o usuário %s: %s", chat_id, exc)
                elif "Chat not found" in reason or "chat not found" in reason.lower() or "bot was blocked by the user" in reason.lower():
                    logger.warning("Não foi possível enviar para o usuário %s porque o chat do Telegram não foi encontrado ou o bot não tem acesso. O usuário precisa iniciar o bot primeiro.", chat_id)
                else:
                    logger.warning("Falha ao enviar notificação para o usuário %s: %s", chat_id, exc)

        return sent

    def _build_message(self, product: Product, drop_event: dict) -> str:
        previous_price = drop_event.get("previous_price", Decimal("0"))
        new_price = drop_event.get("new_price", Decimal("0"))
        difference = drop_event.get("difference", Decimal("0"))

        return (
            f"🚨 Queda de preço detectada!\n\n"
            f"📖 Livro: {product.title or product.asin}\n\n"
            f"💸 De: R$ {previous_price:.2f}\n"
            f"🔥 Por: R$ {new_price:.2f}\n\n"
            f"O preço pode subir novamente a qualquer momento."
        )
