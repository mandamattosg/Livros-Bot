from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.worker_lock import WorkerLock
from app.utils.datetime_utc import ensure_utc, utc_now


class WorkerLockService:
    """Gerencia locks persistentes para processos worker."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _utcnow(self) -> datetime:
        return utc_now()

    def acquire(self, worker_name: str, owner_id: str, ttl_seconds: int) -> bool:
        now = self._utcnow()
        expires_at = now + timedelta(seconds=max(ttl_seconds, 1))

        lock = self.db.query(WorkerLock).filter(WorkerLock.worker_name == worker_name).first()
        if lock is None:
            self.db.add(WorkerLock(worker_name=worker_name, owner_id=owner_id, expires_at=expires_at))
            try:
                self.db.commit()
                return True
            except IntegrityError:
                self.db.rollback()
                lock = self.db.query(WorkerLock).filter(WorkerLock.worker_name == worker_name).first()

        if lock is None:
            return False

        current_expires_at = ensure_utc(lock.expires_at)
        if lock.owner_id != owner_id and current_expires_at is not None and current_expires_at > now:
            return False

        lock.owner_id = owner_id
        lock.acquired_at = now
        # Renew the lease when taking over an expired lock.
        lock.expires_at = expires_at
        self.db.commit()
        return True

    def refresh(self, worker_name: str, owner_id: str, ttl_seconds: int) -> bool:
        lock = self.db.query(WorkerLock).filter(WorkerLock.worker_name == worker_name).first()
        if lock is None or lock.owner_id != owner_id:
            return False

        lock.expires_at = self._utcnow() + timedelta(seconds=max(ttl_seconds, 1))
        self.db.commit()
        return True

    def release(self, worker_name: str, owner_id: str) -> None:
        lock = self.db.query(WorkerLock).filter(WorkerLock.worker_name == worker_name).first()
        if lock is None or lock.owner_id != owner_id:
            return

        self.db.delete(lock)
        self.db.commit()