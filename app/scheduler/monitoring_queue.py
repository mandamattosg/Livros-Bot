from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.monitoring_queue import MonitoringQueue as MonitoringQueueItem
from app.models.product import Product
from app.utils.datetime_utc import utc_now


@dataclass(frozen=True)
class ProductMonitoringJob:
    """Unidade de trabalho para monitoramento de um produto."""

    queue_id: int
    product_id: int


class MonitoringQueueService:
    """Fila persistente de monitoramento, semelhante ao padrão do Kindle-Bot."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _utcnow(self) -> datetime:
        return utc_now()

    def enqueue_products(self, products: list[Product]) -> int:
        if not products:
            return 0

        product_ids = [product.id for product in products if product.id is not None]
        if not product_ids:
            return 0

        active_statuses = ("pending", "processing")
        existing_items = (
            self.db.query(MonitoringQueueItem.product_id)
            .filter(
                MonitoringQueueItem.product_id.in_(product_ids),
                MonitoringQueueItem.status.in_(active_statuses),
            )
            .all()
        )
        existing_product_ids = {product_id for (product_id,) in existing_items}

        queued = 0
        for product in products:
            if product.id is None or product.id in existing_product_ids:
                continue

            self.db.add(MonitoringQueueItem(product_id=product.id, status="pending"))
            queued += 1

        if queued > 0:
            self.db.commit()

        return queued

    def claim_pending_jobs(self, max_items: int) -> list[ProductMonitoringJob]:
        now = self._utcnow()
        items = (
            self.db.query(MonitoringQueueItem)
            .filter(
                MonitoringQueueItem.status == "pending",
                MonitoringQueueItem.available_at <= now,
            )
            .order_by(MonitoringQueueItem.created_at.asc(), MonitoringQueueItem.id.asc())
            .limit(max_items)
            .all()
        )
        if not items:
            return []

        for item in items:
            item.status = "processing"
            item.claimed_at = now
            item.updated_at = now

        self.db.commit()

        return [ProductMonitoringJob(queue_id=item.id, product_id=item.product_id) for item in items]

    def mark_completed(self, queue_id: int) -> None:
        item = self.db.query(MonitoringQueueItem).filter(MonitoringQueueItem.id == queue_id).first()
        if item is None:
            return

        item.status = "completed"
        item.last_error = None
        now = self._utcnow()
        item.updated_at = now
        item.processed_at = now
        self.db.commit()

    def mark_skipped(self, queue_id: int, reason: str) -> None:
        item = self.db.query(MonitoringQueueItem).filter(MonitoringQueueItem.id == queue_id).first()
        if item is None:
            return

        item.status = "skipped"
        item.last_error = reason[:500]
        now = self._utcnow()
        item.updated_at = now
        item.processed_at = now
        self.db.commit()

    def mark_retry_or_failed(self, queue_id: int, error: str, max_retries: int, delay_seconds: int = 0) -> str:
        item = self.db.query(MonitoringQueueItem).filter(MonitoringQueueItem.id == queue_id).first()
        if item is None:
            return "failed"

        now = self._utcnow()
        item.retry_count += 1
        item.last_error = error[:500]
        item.updated_at = now
        if item.retry_count >= max_retries:
            item.status = "failed"
            item.processed_at = now
            self.db.commit()
            return "failed"

        item.status = "pending"
        item.claimed_at = None
        item.available_at = now + timedelta(seconds=max(delay_seconds, 0))
        self.db.commit()
        return "requeued"

    def reset_stuck_processing(self, max_minutes: int) -> int:
        threshold = self._utcnow() - timedelta(minutes=max(max_minutes, 1))
        items = (
            self.db.query(MonitoringQueueItem)
            .filter(
                MonitoringQueueItem.status == "processing",
                MonitoringQueueItem.updated_at < threshold,
            )
            .all()
        )
        if not items:
            return 0

        now = self._utcnow()
        for item in items:
            item.status = "pending"
            item.claimed_at = None
            item.retry_count += 1
            item.last_error = "worker_restart"
            item.available_at = now
            item.updated_at = now

        self.db.commit()
        return len(items)