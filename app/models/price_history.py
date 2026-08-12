from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.sql import func

from app.database.base import Base


class PriceHistory(Base):
    """Histórico de preços de um produto."""

    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
