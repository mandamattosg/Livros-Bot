import unittest
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.monitoring_queue import MonitoringQueue
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.scheduler.worker import MonitoringWorker


class MonitoringWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def _enqueue_monitoring_job(self, product_id: int) -> None:
        self.session.add(MonitoringQueue(product_id=product_id, status="pending"))
        self.session.commit()

    def test_worker_updates_product_and_sends_notification_on_drop(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        user = User(telegram_id="1", username="teste")
        self.session.add_all([product, user])
        self.session.flush()
        self.session.add(UserProduct(user_id=user.id, product_id=product.id))
        self.session.add(PriceHistory(product_id=product.id, price=Decimal("50.00")))
        self.session.commit()
        self._enqueue_monitoring_job(product.id)

        mocked_response = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "6528101965",
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Atualizado"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"amount": 40.00}}]},
                    }
                ]
            }
        }

        with patch("app.services.update_service.AmazonClient.get_items", return_value=mocked_response), patch(
            "app.services.notification_service.requests.post"
        ) as mock_post, patch("app.scheduler.worker.send_monitoring_execution_report"):
            mock_post.return_value.content = b'{"ok": true}'
            mock_post.return_value.json.return_value = {"ok": True}
            results = MonitoringWorker(self.Session, batch_size=5).drain_pending()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "updated")
        self.assertTrue(results[0]["drop_detected"])
        self.assertEqual(results[0]["notifications_queued"], 1)
        self.assertEqual(self.session.query(PriceHistory).count(), 2)
        self.assertEqual(self.session.query(NotificationQueue).count(), 1)
        self.assertEqual(self.session.query(MonitoringQueue).first().status, "completed")
        mock_post.assert_not_called()

    def test_worker_updates_product_without_notification_when_price_rises(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.flush()
        self.session.add(PriceHistory(product_id=product.id, price=Decimal("40.00")))
        self.session.commit()
        self._enqueue_monitoring_job(product.id)

        mocked_response = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "6528101965",
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Atualizado"}},
                        "offersV2": {"listings": [{"price": {"amount": 45.00}}]},
                    }
                ]
            }
        }

        with patch("app.services.update_service.AmazonClient.get_items", return_value=mocked_response), patch(
            "app.services.notification_service.requests.post"
        ) as mock_post, patch("app.scheduler.worker.send_monitoring_execution_report"):
            results = MonitoringWorker(self.Session, batch_size=5).drain_pending()

        self.assertEqual(results[0]["status"], "updated")
        self.assertFalse(results[0]["drop_detected"])
        self.assertEqual(results[0]["notifications_queued"], 0)
        self.assertEqual(self.session.query(MonitoringQueue).first().status, "completed")
        mock_post.assert_not_called()

    def test_worker_ignores_drops_smaller_than_four_reais(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        user = User(telegram_id="1", username="teste")
        self.session.add_all([product, user])
        self.session.flush()
        self.session.add(UserProduct(user_id=user.id, product_id=product.id))
        self.session.add(PriceHistory(product_id=product.id, price=Decimal("50.00")))
        self.session.commit()
        self._enqueue_monitoring_job(product.id)

        mocked_response = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "6528101965",
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Atualizado"}},
                        "offersV2": {"listings": [{"price": {"amount": 48.50}}]},
                    }
                ]
            }
        }

        with patch("app.services.update_service.AmazonClient.get_items", return_value=mocked_response):
            results = MonitoringWorker(self.Session, batch_size=5).drain_pending()

        self.assertEqual(results[0]["status"], "updated")
        self.assertFalse(results[0]["drop_detected"])
        self.assertEqual(results[0]["notifications_queued"], 0)
        self.assertEqual(self.session.query(NotificationQueue).count(), 0)

    def test_worker_requeues_job_when_batch_update_fails(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.commit()
        self._enqueue_monitoring_job(product.id)

        with patch("app.services.update_service.AmazonClient.get_items", side_effect=RuntimeError("amazon unavailable")):
            results = MonitoringWorker(self.Session, batch_size=5, max_retries=2).run_once()

        self.assertEqual(results[0]["status"], "requeued")
        queue_item = self.session.query(MonitoringQueue).first()
        self.assertEqual(queue_item.status, "pending")
        self.assertEqual(queue_item.retry_count, 1)