import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.session import cleanup_old_records
from app.models.monitoring_queue import MonitoringQueue
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.scheduler.monitoring_queue import MonitoringQueueService
from app.utils.datetime_utc import utc_now


class MonitoringQueueServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()
        self.service = MonitoringQueueService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_enqueue_products_skips_duplicates_with_pending_job(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.commit()

        self.session.add(MonitoringQueue(product_id=product.id, status="pending"))
        self.session.commit()

        queued = self.service.enqueue_products([product])

        self.assertEqual(queued, 0)
        self.assertEqual(self.session.query(MonitoringQueue).count(), 1)

    def test_claim_pending_jobs_marks_items_processing(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.commit()

        self.session.add(MonitoringQueue(product_id=product.id, status="pending"))
        self.session.commit()

        jobs = self.service.claim_pending_jobs(5)

        self.assertEqual(len(jobs), 1)
        item = self.session.query(MonitoringQueue).first()
        self.assertEqual(item.status, "processing")

    def test_reset_stuck_processing_requeues_old_jobs(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.commit()

        self.session.add(
            MonitoringQueue(
                product_id=product.id,
                status="processing",
                updated_at=utc_now() - timedelta(minutes=20),
                available_at=utc_now() - timedelta(minutes=20),
            )
        )
        self.session.commit()

        recovered = self.service.reset_stuck_processing(10)

        item = self.session.query(MonitoringQueue).first()
        self.assertEqual(recovered, 1)
        self.assertEqual(item.status, "pending")
        self.assertEqual(item.retry_count, 1)

    def test_cleanup_old_records_removes_data_older_than_60_days(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.commit()

        self.session.add(
            PriceHistory(
                product_id=product.id,
                price=12.99,
                checked_at=utc_now() - timedelta(days=61),
            )
        )
        self.session.add(
            PriceHistory(
                product_id=product.id,
                price=14.50,
                checked_at=utc_now() - timedelta(days=10),
            )
        )
        self.session.add(
            NotificationQueue(
                user_id=1,
                product_id=product.id,
                message="Oferta",
                status="sent",
                sent_at=utc_now() - timedelta(days=61),
                created_at=utc_now() - timedelta(days=61),
                available_at=utc_now() - timedelta(days=61),
                updated_at=utc_now() - timedelta(days=61),
            )
        )
        self.session.add(
            NotificationQueue(
                user_id=1,
                product_id=product.id,
                message="Nova oferta",
                status="sent",
                sent_at=utc_now() - timedelta(days=5),
                created_at=utc_now() - timedelta(days=5),
                available_at=utc_now() - timedelta(days=5),
                updated_at=utc_now() - timedelta(days=5),
            )
        )
        self.session.commit()

        cleanup_old_records(self.session, max_days=60)

        self.assertEqual(self.session.query(PriceHistory).count(), 1)
        self.assertEqual(self.session.query(NotificationQueue).count(), 1)
        self.assertEqual(self.session.query(PriceHistory).first().price, 14.50)