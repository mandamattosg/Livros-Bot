import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.base import Base
from app.models.monitoring_queue import MonitoringQueue
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.admin_report_service import build_admin_report_message, get_admin_report_stats


class AdminReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_get_admin_report_stats_returns_expected_metrics(self) -> None:
        user_active = User(telegram_id="1", username="active", is_active=True)
        user_inactive = User(telegram_id="2", username="inactive", is_active=False)
        product_a = Product(asin="A1", title="Livro A")
        product_b = Product(asin="B1", title="Livro B")
        self.session.add_all([user_active, user_inactive, product_a, product_b])
        self.session.flush()

        self.session.add_all([
            UserProduct(user_id=user_active.id, product_id=product_a.id),
            UserProduct(user_id=user_inactive.id, product_id=product_a.id),
            UserProduct(user_id=user_active.id, product_id=product_b.id),
        ])

        self.session.add_all([
            MonitoringQueue(product_id=product_a.id, status="pending"),
            MonitoringQueue(product_id=product_b.id, status="processing"),
            NotificationQueue(user_id=user_active.id, product_id=product_a.id, message="x", status="pending"),
            NotificationQueue(user_id=user_active.id, product_id=product_b.id, message="y", status="sending"),
            PriceHistory(product_id=product_a.id, price=10.0),
        ])
        self.session.commit()

        with patch.object(settings, "REFRESH_HIGH_MONITOR_MIN_USERS", 2):
            stats = get_admin_report_stats(self.session)

        self.assertEqual(stats["hot_products"], 1)
        self.assertEqual(stats["cold_products"], 1)
        self.assertEqual(stats["total_users"], 2)
        self.assertEqual(stats["active_users"], 1)
        self.assertEqual(stats["users_monitoring"], 1)
        self.assertEqual(stats["products_monitored"], 2)
        self.assertEqual(stats["total_monitorings"], 3)
        self.assertEqual(stats["top_product"], "Livro A")
        self.assertEqual(stats["top_product_monitors"], 2)
        self.assertEqual(stats["pending_monitoring_jobs"], 2)
        self.assertEqual(stats["pending_notification_jobs"], 2)
        self.assertIsNotNone(stats["last_price_update_at"])

    def test_build_admin_report_message_formats_payload(self) -> None:
        now = datetime(2026, 8, 8, 12, 30, 0, tzinfo=timezone.utc)
        message = build_admin_report_message(
            {
                "total_users": 10,
                "active_users": 9,
                "users_monitoring": 7,
                "products_monitored": 5,
                "hot_products": 2,
                "cold_products": 3,
                "total_monitorings": 12,
                "top_product": "Livro X",
                "top_product_monitors": 4,
                "pending_monitoring_jobs": 3,
                "pending_notification_jobs": 2,
                "last_price_update_at": now,
            }
        )

        self.assertIn("Usuários totais: 10", message)
        self.assertIn("Produtos quentes: 2", message)
        self.assertIn("Produtos frios: 3", message)
        self.assertIn("Produto mais monitorado: Livro X (4)", message)
        self.assertIn("Última atualização de preço: 2026-08-08 12:30:00 UTC", message)


if __name__ == "__main__":
    unittest.main()
