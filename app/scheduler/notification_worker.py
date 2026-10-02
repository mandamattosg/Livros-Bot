from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from uuid import uuid4

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import SessionLocal, init_db
from app.logging import get_logger
from app.models.notification_queue import NotificationQueue
from app.models.product import Product
from app.models.user import User
from app.scheduler.worker_lock import WorkerLockService
from app.services.notification_service import NotificationService
from app.utils.datetime_utc import utc_now

logger = get_logger("app.scheduler.notification_worker")


class NotificationWorker:
    """Worker responsável por drenar a fila persistente de notificações."""

    def __init__(self, session_factory=SessionLocal, batch_size: int | None = None, max_retries: int | None = None) -> None:
        self.session_factory = session_factory
        self.batch_size = batch_size or settings.NOTIFICATION_WORKER_BATCH_SIZE
        self.max_retries = max_retries or settings.NOTIFICATION_WORKER_MAX_RETRIES
        self.poll_interval = settings.NOTIFICATION_WORKER_POLL_INTERVAL
        self.batch_sleep = settings.NOTIFICATION_WORKER_BATCH_SLEEP
        self.lock_ttl = settings.NOTIFICATION_WORKER_LOCK_TTL
        self.stuck_minutes = settings.NOTIFICATION_WORKER_STUCK_MINUTES
        self.worker_name = "notification_worker"

    def _utcnow(self) -> datetime:
        return utc_now()

    def drain_pending_batch(self) -> dict[str, int]:
        stats = {"sent": 0, "failed": 0, "requeued": 0, "skipped": 0}

        db = self.session_factory()
        try:
            items = self._claim_pending_notifications(db)
            if not items:
                return stats

            service = NotificationService(db)
            for item in items:
                outcome = self._process_item(db, service, item)
                stats[outcome] += 1
            return stats
        finally:
            db.close()

    def drain_pending(self) -> dict[str, int]:
        stats = {"sent": 0, "failed": 0, "requeued": 0, "skipped": 0}

        while True:
            batch_stats = self.drain_pending_batch()
            if sum(batch_stats.values()) == 0:
                return stats
            for key, value in batch_stats.items():
                stats[key] += value

    def run_forever(self) -> None:
        logger.info("Iniciando notification worker em modo forever; preparando banco de dados.")
        init_db()
        logger.info("Banco preparado; iniciando loop do notification worker.")

        owner_id = f"{os.getpid()}-{uuid4().hex[:8]}"
        lock_db = self.session_factory()
        try:
            lock_service = WorkerLockService(lock_db)
            if not lock_service.acquire(self.worker_name, owner_id, self.lock_ttl):
                logger.warning("Já existe notification worker ativo; aguardando o lock liberar.")
                while True:
                    lock_db.rollback()
                    time.sleep(max(self.poll_interval, 0.2))
                    if lock_service.acquire(self.worker_name, owner_id, self.lock_ttl):
                        logger.info("Lock do notification worker liberado; esta instância assumiu o processamento.")
                        break

            recovered = self._reset_stuck_sending_notifications()
            if recovered > 0:
                logger.info("Notification worker recuperou %s item(ns) presos em sending.", recovered)

            logger.info(
                "Notification worker iniciado (batch_size=%s, poll_interval=%.2fs)",
                self.batch_size,
                self.poll_interval,
            )
            while True:
                if not lock_service.refresh(self.worker_name, owner_id, self.lock_ttl):
                    logger.warning("Notification worker perdeu o lock e será encerrado.")
                    return

                stats = self.drain_pending_batch()
                if sum(stats.values()) == 0:
                    time.sleep(max(self.poll_interval, 0.2))
                    continue

                logger.info("Notification worker processou lote: %s", stats)
                time.sleep(max(self.batch_sleep, 0.0))
        finally:
            WorkerLockService(lock_db).release(self.worker_name, owner_id)
            lock_db.close()

    def _claim_pending_notifications(self, db: Session) -> list[NotificationQueue]:
        now = self._utcnow()
        items = (
            db.query(NotificationQueue)
            .filter(
                NotificationQueue.status == "pending",
                NotificationQueue.available_at <= now,
            )
            .order_by(NotificationQueue.created_at.asc(), NotificationQueue.id.asc())
            .limit(self.batch_size)
            .all()
        )
        if not items:
            return []

        for item in items:
            item.status = "sending"
            item.updated_at = now

        db.commit()
        return items

    def _process_item(self, db: Session, service: NotificationService, item: NotificationQueue) -> str:
        user = db.query(User).filter(User.id == item.user_id).first()
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not user or not getattr(user, "is_active", True) or not product:
            item.status = "skipped"
            item.last_error = "missing_user_or_product"
            item.updated_at = self._utcnow()
            db.commit()
            return "skipped"

        chat_id = service._normalize_chat_id(user.telegram_id)
        if chat_id is None:
            item.status = "skipped"
            item.last_error = "missing_chat_id"
            item.updated_at = self._utcnow()
            db.commit()
            return "skipped"

        try:
            service._send_message(chat_id, item.message, product)
            item.status = "sent"
            now = self._utcnow()
            item.sent_at = now
            item.updated_at = now
            item.last_error = None
            db.commit()
            return "sent"
        except Exception as exc:
            item.last_error = str(exc)[:500]
            item.updated_at = self._utcnow()
            if item.retry_count + 1 >= self.max_retries:
                item.retry_count += 1
                item.status = "failed"
                db.commit()
                return "failed"

            item.retry_count += 1
            item.status = "pending"
            item.available_at = self._utcnow() + timedelta(seconds=min(60, 2 ** min(item.retry_count, 5)))
            db.commit()
            return "requeued"

    def _reset_stuck_sending_notifications(self) -> int:
        db = self.session_factory()
        try:
            threshold = self._utcnow() - timedelta(minutes=max(self.stuck_minutes, 1))
            items = (
                db.query(NotificationQueue)
                .filter(
                    NotificationQueue.status == "sending",
                    NotificationQueue.updated_at < threshold,
                )
                .all()
            )
            if not items:
                return 0

            now = self._utcnow()
            for item in items:
                item.status = "pending"
                item.retry_count += 1
                item.available_at = now
                item.updated_at = now
                item.last_error = "worker_restart"

            db.commit()
            return len(items)
        finally:
            db.close()


def run_notification_worker_once() -> dict[str, int]:
    init_db()
    return NotificationWorker().drain_pending()


def run_notification_worker_forever() -> None:
    NotificationWorker().run_forever()


if __name__ == "__main__":
    if os.getenv("NOTIFICATION_WORKER_MODE", "once").strip().lower() == "forever":
        run_notification_worker_forever()
    else:
        summary = run_notification_worker_once()
        logger.info("Notification worker finalizou: %s", summary)