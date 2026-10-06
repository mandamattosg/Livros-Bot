from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.sql import func

from app.database.base import Base


class UserProduct(Base):
    """Relação entre usuário e produto monitorado."""

    __tablename__ = "user_products"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_products_user_product"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
