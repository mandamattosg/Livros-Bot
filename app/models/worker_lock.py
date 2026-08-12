from __future__ import annotations

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.database.base import Base


class WorkerLock(Base):
    """Lock persistente para evitar workers duplicados do mesmo tipo."""

    __tablename__ = "worker_locks"

    worker_name = Column(String, primary_key=True, index=True)
    owner_id = Column(String, nullable=False)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)