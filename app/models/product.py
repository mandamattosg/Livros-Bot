from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database.base import Base


class Product(Base):
    """Produto monitorado pelo bot."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    asin = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    image_url = Column(Text, nullable=True)
    affiliate_link = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
