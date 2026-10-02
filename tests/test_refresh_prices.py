import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.base import Base
from app.models.monitoring_queue import MonitoringQueue
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services import refresh_prices as refresh_module
from app.utils.datetime_utc import utc_now


class RefreshPricesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def _create_users_for_product(self, product: Product, total_users: int, offset: int = 0) -> None:
        users = [
            User(telegram_id=f"{offset + index + 1}", username=f"user_{offset + index + 1}")
            for index in range(total_users)
        ]
        self.session.add_all(users)
        self.session.flush()

        links = [UserProduct(user_id=user.id, product_id=product.id) for user in users]
        self.session.add_all(links)
        self.session.flush()

    def test_select_products_for_refresh_applies_tier_intervals(self) -> None:
        now = utc_now()
        high_eligible = Product(asin="ASIN-H-1", title="High Eligible")
        high_ineligible = Product(asin="ASIN-H-2", title="High Ineligible")
        low_eligible = Product(asin="ASIN-L-1", title="Low Eligible")
        low_ineligible = Product(asin="ASIN-L-2", title="Low Ineligible")
        low_without_monitors = Product(asin="ASIN-L-3", title="Low No Monitors")
        self.session.add_all([high_eligible, high_ineligible, low_eligible, low_ineligible, low_without_monitors])
        self.session.flush()

        self._create_users_for_product(high_eligible, 3, 0)
        self._create_users_for_product(high_ineligible, 3, 10)
        self._create_users_for_product(low_eligible, 1, 20)
        self._create_users_for_product(low_ineligible, 1, 30)

        self.session.add_all([
            MonitoringQueue(
                product_id=high_eligible.id,
                status="completed",
                processed_at=now - timedelta(hours=7),
                updated_at=now - timedelta(hours=7),
            ),
            MonitoringQueue(
                product_id=high_ineligible.id,
                status="completed",
                processed_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=2),
            ),
            MonitoringQueue(
                product_id=low_eligible.id,
                status="completed",
                processed_at=now - timedelta(hours=13),
                updated_at=now - timedelta(hours=13),
            ),
            MonitoringQueue(
                product_id=low_ineligible.id,
                status="completed",
                processed_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=2),
            ),
        ])
        self.session.commit()

        with (
            patch.object(settings, "REFRESH_HIGH_MONITOR_MIN_USERS", 3),
            patch.object(settings, "REFRESH_HIGH_MONITOR_INTERVAL_HOURS", 6),
            patch.object(settings, "REFRESH_LOW_MONITOR_INTERVAL_HOURS", 12),
        ):
            eligible_products, stats = refresh_module._select_products_for_refresh(self.session, now)

        eligible_asins = {product.asin for product in eligible_products}
        self.assertEqual(eligible_asins, {"ASIN-H-1", "ASIN-L-1", "ASIN-L-3"})

        self.assertEqual(stats["products_found"], 5)
        self.assertEqual(stats["high_frequency_products"], 2)
        self.assertEqual(stats["low_frequency_products"], 3)
        self.assertEqual(stats["eligible_high_frequency"], 1)
        self.assertEqual(stats["eligible_low_frequency"], 2)

    def test_zero_intervals_make_recently_checked_products_eligible(self) -> None:
        now = utc_now()
        high_product = Product(asin="ASIN-ZERO-H", title="High immediate")
        low_product = Product(asin="ASIN-ZERO-L", title="Low immediate")
        self.session.add_all([high_product, low_product])
        self.session.flush()

        self._create_users_for_product(high_product, 3)
        self._create_users_for_product(low_product, 1, 10)

        checked_recently = now - timedelta(minutes=5)
        self.session.add_all([
            MonitoringQueue(
                product_id=high_product.id,
                status="completed",
                processed_at=checked_recently,
                updated_at=checked_recently,
            ),
            MonitoringQueue(
                product_id=low_product.id,
                status="completed",
                processed_at=checked_recently,
                updated_at=checked_recently,
            ),
        ])
        self.session.commit()

        with (
            patch.object(settings, "REFRESH_HIGH_MONITOR_MIN_USERS", 3),
            patch.object(settings, "REFRESH_HIGH_MONITOR_INTERVAL_HOURS", 0),
            patch.object(settings, "REFRESH_LOW_MONITOR_INTERVAL_HOURS", 0),
        ):
            eligible_products, stats = refresh_module._select_products_for_refresh(self.session, now)

        self.assertEqual({product.asin for product in eligible_products}, {"ASIN-ZERO-H", "ASIN-ZERO-L"})
        self.assertEqual(stats["eligible_high_frequency"], 1)
        self.assertEqual(stats["eligible_low_frequency"], 1)

    def test_refresh_prices_returns_segmented_summary(self) -> None:
        now = utc_now()
        high_product = Product(asin="ASIN-SEG-1", title="High")
        low_product = Product(asin="ASIN-SEG-2", title="Low")
        self.session.add_all([high_product, low_product])
        self.session.flush()

        self._create_users_for_product(high_product, 3)
        self._create_users_for_product(low_product, 1, 10)

        self.session.add(
            MonitoringQueue(
                product_id=low_product.id,
                status="completed",
                processed_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
            )
        )
        self.session.commit()

        with (
            patch.object(refresh_module, "SessionLocal", self.Session),
            patch.object(refresh_module, "init_db", lambda: None),
            patch.object(settings, "REFRESH_HIGH_MONITOR_MIN_USERS", 3),
            patch.object(settings, "REFRESH_HIGH_MONITOR_INTERVAL_HOURS", 6),
            patch.object(settings, "REFRESH_LOW_MONITOR_INTERVAL_HOURS", 12),
        ):
            summary = refresh_module.refresh_prices()

        self.assertEqual(summary["products_found"], 2)
        self.assertEqual(summary["high_frequency_products"], 1)
        self.assertEqual(summary["low_frequency_products"], 1)
        self.assertEqual(summary["eligible_high_frequency"], 1)
        self.assertEqual(summary["eligible_low_frequency"], 0)
        self.assertEqual(summary["eligible_total"], 1)
        self.assertEqual(summary["jobs_enqueued"], 1)


if __name__ == "__main__":
    unittest.main()
