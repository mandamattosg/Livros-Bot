from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database.base import Base

INVALID_LINK = "invalid_link"
LINK_NOT_AT_START = "link_not_at_start"
AMAZON_ERROR = "amazon_error"
PRODUCT_NOT_FOUND = "product_not_found"
LIMIT_REACHED = "limit_reached"
UNEXPECTED_ERROR = "unexpected_error"

REASON_LABELS: dict[str, str] = {
    LINK_NOT_AT_START: "Link no meio do texto",
    INVALID_LINK: "Link inválido",
    AMAZON_ERROR: "Erro ao consultar a Amazon",
    PRODUCT_NOT_FOUND: "Produto não encontrado",
    LIMIT_REACHED: "Limite de produtos atingido",
    UNEXPECTED_ERROR: "Erro inesperado",
}


class RegistrationFailure(Base):
    """Tentativa de cadastro de produto que não resultou em monitoramento."""

    __tablename__ = "registration_failures"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reason = Column(String(40), nullable=False, index=True)
    link = Column(String(500), nullable=True)
    detail = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
