import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.notification_queue import NotificationQueue
from app.models.product import Product
from app.models.user import User
from app.scheduler.notification_worker import NotificationWorker
from app.utils.datetime_utc import utc_now


class NotificationWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_worker_sends_pending_notifications(self) -> None:
        user = User(telegram_id="123", username="teste")
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add_all([user, product])
        self.session.flush()
        self.session.add(
            NotificationQueue(
                user_id=user.id,
                product_id=product.id,
                message="alerta",
                button_url="https://example.com",
            )
        )
        self.session.commit()

        with patch("app.services.notification_service.requests.post") as mock_post:
            mock_post.return_value.content = b'{"ok": true}'
            mock_post.return_value.json.return_value = {"ok": True}
            summary = NotificationWorker(self.Session, batch_size=5, max_retries=2).drain_pending()

        item = self.session.query(NotificationQueue).first()
        self.assertEqual(summary["sent"], 1)
        self.assertEqual(item.status, "sent")
        self.assertIsInstance(item.sent_at, datetime)

    def test_worker_marks_item_failed_after_max_retries(self) -> None:
        user = User(telegram_id="123", username="teste")
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add_all([user, product])
        self.session.flush()
        self.session.add(
            NotificationQueue(
                user_id=user.id,
                product_id=product.id,
                message="alerta",
                button_url="https://example.com",
            )
        )
        self.session.commit()

        with patch("app.services.notification_service.requests.post", side_effect=RuntimeError("send failed")):
            summary = NotificationWorker(self.Session, batch_size=5, max_retries=1).drain_pending()

        item = self.session.query(NotificationQueue).first()
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(item.status, "failed")

    def test_worker_recovers_stuck_sending_items(self) -> None:
        user = User(telegram_id="123", username="teste")
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add_all([user, product])
        self.session.flush()
        self.session.add(
            NotificationQueue(
                user_id=user.id,
                product_id=product.id,
                message="alerta",
                status="sending",
                updated_at=utc_now() - timedelta(minutes=20),
                available_at=utc_now() - timedelta(minutes=20),
            )
        )
        self.session.commit()

        recovered = NotificationWorker(self.Session, batch_size=5, max_retries=2)._reset_stuck_sending_notifications()

        item = self.session.query(NotificationQueue).first()
        self.assertEqual(recovered, 1)
        self.assertEqual(item.status, "pending")
        self.assertEqual(item.retry_count, 1)