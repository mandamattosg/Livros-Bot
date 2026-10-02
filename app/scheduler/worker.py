from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.logging import get_logger
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.scheduler.monitoring_queue import MonitoringQueueService, ProductMonitoringJob
from app.scheduler.notification_queue import NotificationQueueService
from app.scheduler.worker_lock import WorkerLockService
from app.services.monitoring_execution_report_service import send_monitoring_execution_report
from app.services.price_drop_service import PriceDropService
from app.services.update_service import UpdateService


logger = get_logger("app.scheduler.worker")


@dataclass
class MonitoringResult:
    """Resultado do processamento de monitoramento de um produto."""

    product_id: int
    asin: str | None
    status: str
    price: float | None = None
    drop_detected: bool = False
    notifications_queued: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "product_id": self.product_id,
            "asin": self.asin,
            "status": self.status,
            "drop_detected": self.drop_detected,
            "notifications_queued": self.notifications_queued,
        }
        if self.price is not None:
            payload["price"] = self.price
        return payload


class MonitoringWorker:
    """Worker responsável por drenar a fila persistente de monitoramento."""

    def __init__(self, session_factory: Callable[[], Session], batch_size: int | None = None, max_retries: int | None = None) -> None:
        self.session_factory = session_factory
        self.batch_size = batch_size or settings.MONITORING_WORKER_BATCH_SIZE
        self.max_retries = max_retries or settings.MONITORING_WORKER_MAX_RETRIES
        self.poll_interval = settings.MONITORING_WORKER_POLL_INTERVAL
        self.batch_sleep = settings.MONITORING_WORKER_BATCH_SLEEP
        self.lock_ttl = settings.MONITORING_WORKER_LOCK_TTL
        self.stuck_minutes = settings.MONITORING_WORKER_STUCK_MINUTES
        self.worker_name = "monitoring_worker"

    def drain_pending(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start_time = time.time()
        while True:
            batch = self.run_once()
            if not batch:
                execution_time = time.time() - start_time
                if results:
                    send_monitoring_execution_report(results, execution_time)
                return results
            results.extend(batch)

    def run_once(self) -> list[dict[str, Any]]:
        db = self.session_factory()
        try:
            queue = MonitoringQueueService(db)
            jobs = queue.claim_pending_jobs(self.batch_size)
            if not jobs:
                return []
            return self._process_jobs(db, queue, jobs)
        finally:
            db.close()

    def run_forever(self) -> None:
        owner_id = f"{uuid4().hex[:8]}-{self.worker_name}"
        lock_db = self.session_factory()
        try:
            lock_service = WorkerLockService(lock_db)
            if not lock_service.acquire(self.worker_name, owner_id, self.lock_ttl):
                logger.warning("Já existe monitoring worker ativo; aguardando o lock liberar.")
                while True:
                    lock_db.rollback()
                    time.sleep(max(self.poll_interval, 0.2))
                    if lock_service.acquire(self.worker_name, owner_id, self.lock_ttl):
                        logger.info("Lock do monitoring worker liberado; esta instância assumiu o processamento.")
                        break

            recovered = self._reset_stuck_processing_jobs()
            if recovered > 0:
                logger.info("Monitoring worker recuperou %s item(ns) presos em processing.", recovered)

            logger.info(
                "Monitoring worker iniciado (batch_size=%s, poll_interval=%.2fs)",
                self.batch_size,
                self.poll_interval,
            )
            while True:
                try:
                    lock_is_owned = lock_service.refresh(self.worker_name, owner_id, self.lock_ttl)
                except Exception:
                    lock_db.rollback()
                    logger.exception("Falha ao renovar lock do monitoring worker; tentando novamente")
                    time.sleep(min(max(self.poll_interval, 0.2), 30.0))
                    continue

                if not lock_is_owned:
                    logger.warning("Monitoring worker perdeu o lock e será encerrado.")
                    return

                batch_start_time = time.time()
                try:
                    results = self.run_once()
                except Exception:
                    logger.exception("Falha transitÃ³ria no monitoring worker; tentando novamente")
                    lock_db.rollback()
                    time.sleep(min(max(self.poll_interval, 0.2), 30.0))
                    continue
                if not results:
                    time.sleep(max(self.poll_interval, 0.2))
                    continue

                batch_execution_time = time.time() - batch_start_time
                logger.info("Monitoring worker processou %s item(ns).", len(results))
                for result in results:
                    logger.info("Resultado do monitoring worker: %s", result)
                try:
                    send_monitoring_execution_report(results, batch_execution_time)
                except Exception:
                    logger.exception("Falha ao enviar relatÃ³rio do monitoring worker")
                time.sleep(max(self.batch_sleep, 0.0))
        finally:
            try:
                lock_db.rollback()
                WorkerLockService(lock_db).release(self.worker_name, owner_id)
            except Exception:
                logger.exception("Falha ao liberar lock do monitoring worker")
            lock_db.close()

    def _process_jobs(
        self,
        db: Session,
        queue: MonitoringQueueService,
        jobs: list[ProductMonitoringJob],
    ) -> list[dict[str, Any]]:
        batch_results: list[dict[str, Any]] = []
        update_service = UpdateService(db)
        drop_service = PriceDropService()
        notification_queue_service = NotificationQueueService(db)

        product_ids = [job.product_id for job in jobs]
        jobs_by_product_id = {job.product_id: job for job in jobs}
        products = self._load_products(db, product_ids)
        ordered_products = [products[product_id] for product_id in product_ids if product_id in products]
        previous_prices = self._load_latest_prices(db, [product.id for product in ordered_products])

        missing_product_ids = [product_id for product_id in product_ids if product_id not in products]
        for product_id in missing_product_ids:
            queue.mark_skipped(jobs_by_product_id[product_id].queue_id, "missing_product")
            batch_results.append(MonitoringResult(product_id=product_id, asin=None, status="missing_product").as_dict())

        results_by_product_id: dict[int, MonitoringResult] = {
            product.id: MonitoringResult(product_id=product.id, asin=product.asin, status="processing")
            for product in ordered_products
        }

        try:
            update_results = update_service.update_products(ordered_products)
        except Exception as exc:
            error_message = str(exc) or exc.__class__.__name__
            for job in jobs:
                outcome = queue.mark_retry_or_failed(job.queue_id, error_message, self.max_retries, delay_seconds=2)
                batch_results.append(
                    MonitoringResult(
                        product_id=job.product_id,
                        asin=products[job.product_id].asin if job.product_id in products else None,
                        status=outcome,
                    ).as_dict()
                )
            return batch_results

        for product, update_result in zip(ordered_products, update_results):
            result = results_by_product_id[product.id]
            result.status = update_result.get("status", "unknown")
            if "price" in update_result:
                result.price = float(update_result["price"])

            job_id = jobs_by_product_id[product.id].queue_id

            if result.status == "rate_limited":
                # Rate limit: reenfileirar com delay maior (30 segundos)
                queue.mark_retry_or_failed(job_id, "Rate limit da Amazon", self.max_retries, delay_seconds=30)
                batch_results.append(result.as_dict())
                continue

            if result.status == "updated":
                latest_price = self._load_latest_price(db, product.id)
                drop_event = drop_service.detect_drop_from_prices(
                    product,
                    previous_prices.get(product.id),
                    latest_price,
                )
                if drop_event is not None:
                    result.drop_detected = True
                    result.notifications_queued = notification_queue_service.enqueue_drop_notifications(drop_event, product)

            queue.mark_completed(job_id)
            batch_results.append(result.as_dict())

        return batch_results

    def _load_products(self, db: Session, product_ids: list[int]) -> dict[int, Product]:
        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        return {product.id: product for product in products}

    def _load_latest_prices(self, db: Session, product_ids: list[int]) -> dict[int, Decimal]:
        if not product_ids:
            return {}

        latest_per_product = (
            db.query(
                PriceHistory.product_id.label("product_id"),
                func.max(PriceHistory.id).label("max_id"),
            )
            .filter(PriceHistory.product_id.in_(product_ids))
            .group_by(PriceHistory.product_id)
            .subquery()
        )

        rows = (
            db.query(PriceHistory.product_id, PriceHistory.price)
            .join(latest_per_product, PriceHistory.id == latest_per_product.c.max_id)
            .all()
        )

        return {
            product_id: Decimal(str(price))
            for product_id, price in rows
            if price is not None
        }

    def _load_latest_price(self, db: Session, product_id: int) -> Decimal | None:
        latest_entry = (
            db.query(PriceHistory)
            .filter(PriceHistory.product_id == product_id)
            .order_by(PriceHistory.checked_at.desc(), PriceHistory.id.desc())
            .first()
        )
        if latest_entry is None or latest_entry.price is None:
            return None
        return Decimal(str(latest_entry.price))

    def _reset_stuck_processing_jobs(self) -> int:
        db = self.session_factory()
        try:
            return MonitoringQueueService(db).reset_stuck_processing(self.stuck_minutes)
        finally:
            db.close()
