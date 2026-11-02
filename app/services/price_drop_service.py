from __future__ import annotations

from decimal import Decimal

from app.config import settings
from app.models.price_history import PriceHistory
from app.models.product import Product


class PriceDropService:
    """Serviço responsável por detectar quedas de preço a partir do histórico."""

    def __init__(
        self,
        minimum_drop_amount: Decimal | float | str | None = None,
        minimum_drop_percentage: Decimal | float | str | None = None,
    ) -> None:
        configured_amount = minimum_drop_amount if minimum_drop_amount is not None else settings.PRICE_DROP_MINIMUM
        configured_percentage = (
            minimum_drop_percentage if minimum_drop_percentage is not None else settings.PRICE_DROP_MINIMUM_PERCENTAGE
        )
        self.minimum_drop_amount = Decimal(str(configured_amount))
        self.minimum_drop_percentage = Decimal(str(configured_percentage))

    def detect_drop(self, product: Product) -> dict | None:
        """Compara o último preço registrado com o preço anterior e retorna um evento se houve queda."""

        history = (
            product.price_history
            if hasattr(product, "price_history")
            else []
        )

        if len(history) < 2:
            return None

        latest = history[-1]
        previous = history[-2]
        latest_price = Decimal(str(latest.price))
        previous_price = Decimal(str(previous.price))

        return self.detect_drop_from_prices(product, previous_price, latest_price)

    def detect_drop_from_prices(
        self,
        product: Product,
        previous_price: Decimal | float | str | None,
        latest_price: Decimal | float | str | None,
    ) -> dict | None:
        """Compara dois preços e retorna um evento se houve queda."""

        if previous_price is None or latest_price is None:
            return None

        normalized_previous = Decimal(str(previous_price))
        normalized_latest = Decimal(str(latest_price))

        if normalized_latest < normalized_previous:
            difference = normalized_previous - normalized_latest
            if difference < self.minimum_drop_amount:
                return None
            if difference * 100 < normalized_previous * self.minimum_drop_percentage:
                return None

            percentage = (difference / normalized_previous * 100) if normalized_previous else Decimal("0")
            return {
                "product_id": product.id,
                "asin": product.asin,
                "previous_price": normalized_previous,
                "new_price": normalized_latest,
                "difference": difference,
                "percentage": round(percentage, 2),
                "minimum_drop_amount": self.minimum_drop_amount,
                "minimum_drop_percentage": self.minimum_drop_percentage,
            }

        return None
