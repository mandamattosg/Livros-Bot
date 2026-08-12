from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notification_queue import NotificationQueue
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.notification_service import NotificationService
from app.utils.datetime_utc import utc_now


class NotificationQueueService:
    """Enfileira notificações persistentes para envio assíncrono."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.notification_service = NotificationService(db)

    def enqueue_drop_notifications(self, drop_event: dict, product: Product) -> int:
        relations = self.db.query(UserProduct).filter(UserProduct.product_id == product.id).all()
        if not relations:
            return 0

        queued = 0
        message = self.notification_service._build_message(product, drop_event)
        button_url = self.notification_service._build_offer_link(product)

        for relation in relations:
            user = self.db.query(User).filter(User.id == relation.user_id).first()
            if not user or not getattr(user, "is_active", True):
                continue

            now = utc_now()

            item = NotificationQueue(
                user_id=user.id,
                product_id=product.id,
                message=message,
                button_url=button_url,
                status="pending",
                available_at=now,
                updated_at=now,
            )
            self.db.add(item)
            queued += 1

        if queued > 0:
            self.db.commit()

        return queued