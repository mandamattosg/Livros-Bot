from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.amazon.client import AmazonRateLimitError
from app.database.base import Base
from app.models.monitoring_queue import MonitoringQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.scheduler.worker import MonitoringWorker
from app.services.update_service import UpdateService


class RateLimitHandlingTests(unittest.TestCase):
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

    def test_update_service_handles_rate_limit_error(self) -> None:
        """Testa que UpdateService retorna 'rate_limited' quando 429 ocorre."""
        product = Product(asin="TEST123", title="Livro Teste")
        self.session.add(product)
        self.session.commit()

        service = UpdateService(self.session)

        with patch.object(
            service.amazon_client, "get_items", side_effect=AmazonRateLimitError("Limite de requisições atingido")
        ):
            results = service.update_products([product])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["asin"], "TEST123")
        self.assertEqual(results[0]["status"], "rate_limited")

    def test_worker_requeues_rate_limited_products_with_delay(self) -> None:
        """Testa que o worker reenfileira produtos com rate limit com delay de 30s."""
        product = Product(asin="TEST429", title="Livro Rate Limited")
        self.session.add(product)
        self.session.flush()
        self.session.add(PriceHistory(product_id=product.id, price=Decimal("50.00")))
        self.session.commit()
        self._enqueue_monitoring_job(product.id)

        initial_queue = self.session.query(MonitoringQueue).first()
        self.assertEqual(initial_queue.status, "pending")
        initial_job_id = initial_queue.id

        with patch.object(
            UpdateService, "update_products", return_value=[{"asin": "TEST429", "status": "rate_limited"}]
        ), patch("app.scheduler.worker.send_monitoring_execution_report"):
            results = MonitoringWorker(self.Session, batch_size=5).drain_pending()

        # Verifica que o resultado marca como rate_limited
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "rate_limited")

        # Cria nova sessão para consultar (simula nova execução do worker)
        new_session = self.Session()
        try:
            queue_item = new_session.query(MonitoringQueue).filter(MonitoringQueue.id == initial_job_id).first()
            # O item deve estar em pending (reenfileirado), e não completed
            self.assertEqual(queue_item.status, "pending")
            self.assertEqual(queue_item.retry_count, 1)
        finally:
            new_session.close()

    def test_rate_limited_products_dont_break_batch(self) -> None:
        """Testa que um rate limit em um produto não quebra o processamento dos outros."""
        product1 = Product(asin="GOOD1", title="Livro Bom 1")
        product2 = Product(asin="RATELIMIT", title="Livro Rate Limited")
        product3 = Product(asin="GOOD2", title="Livro Bom 2")

        self.session.add_all([product1, product2, product3])
        self.session.flush()

        for product in [product1, product2, product3]:
            self.session.add(PriceHistory(product_id=product.id, price=Decimal("50.00")))

        self.session.commit()

        for product in [product1, product2, product3]:
            self._enqueue_monitoring_job(product.id)

        # Simula que a Amazon API retorna rate limit
        def mock_get_items(asins):
            if "RATELIMIT" in asins:
                raise AmazonRateLimitError("Rate limited")
            return {
                "itemsResult": {
                    "items": [
                        {"asin": asin, "offersV2": {"listings": [{"price": {"amount": 45.0}}]}}
                        for asin in asins
                        if asin in ["GOOD1", "GOOD2"]
                    ]
                }
            }

        with patch.object(UpdateService, "__init__", lambda x, db: None), patch.object(
            UpdateService, "update_products"
        ) as mock_update, patch("app.scheduler.worker.send_monitoring_execution_report"):
            service = UpdateService(self.session)
            service.amazon_client = type("MockClient", (), {})()
            service.price_service = type("MockPriceService", (), {"record_prices": lambda *args, **kwargs: None})()

            mock_update.return_value = [
                {"asin": "GOOD1", "status": "updated", "price": 45.0},
                {"asin": "RATELIMIT", "status": "rate_limited"},
                {"asin": "GOOD2", "status": "updated", "price": 45.0},
            ]

            results = MonitoringWorker(self.Session, batch_size=10).drain_pending()

        # Verifica que temos 3 resultados
        self.assertEqual(len(results), 3)

        # Verifica que os bons foram processados e o rate limited foi reenfileirado
        statuses = {r["asin"]: r["status"] for r in results}
        self.assertEqual(statuses.get("GOOD1"), "updated")
        self.assertEqual(statuses.get("RATELIMIT"), "rate_limited")
        self.assertEqual(statuses.get("GOOD2"), "updated")
