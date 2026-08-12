from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.price_history import PriceHistory
from app.models.product import Product


class PriceService:
    """Serviço responsável por registrar o histórico de preços dos produtos."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_price(self, product: Product, price: float | Decimal | str, commit: bool = True) -> PriceHistory:
        """Registra um novo preço no histórico."""

        normalized_price = Decimal(str(price))
        entry = PriceHistory(product_id=product.id, price=normalized_price)
        self.db.add(entry)
        if commit:
            self.db.commit()
            self.db.refresh(entry)
        return entry

    def record_prices(self, product_prices: list[tuple[Product, float | Decimal | str]], commit: bool = True) -> list[PriceHistory]:
        """Registra vários preços de uma vez para reduzir round trips ao banco."""

        entries: list[PriceHistory] = []
        for product, price in product_prices:
            normalized_price = Decimal(str(price))
            entries.append(PriceHistory(product_id=product.id, price=normalized_price))

        if not entries:
            return entries

        self.db.add_all(entries)
        if commit:
            self.db.commit()
        return entries
