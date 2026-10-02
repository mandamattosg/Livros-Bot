from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Integer

from app.database.base import Base


class AmazonApiUsageDaily(Base):
    """Contadores diários de tentativas à Amazon Creators API."""

    __tablename__ = "amazon_api_usage_daily"

    usage_date = Column(Date, primary_key=True)
    total_requests = Column(Integer, nullable=False, default=0)
    successful_requests = Column(Integer, nullable=False, default=0)
    rate_limited_requests = Column(Integer, nullable=False, default=0)
    failed_requests = Column(Integer, nullable=False, default=0)
    report_sent_at = Column(DateTime(timezone=True), nullable=True)
