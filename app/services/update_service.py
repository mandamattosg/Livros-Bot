from __future__ import annotations

import os
import sys
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.orm import Session

from app.amazon.client import AmazonClient
from app.logging import get_logger
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.price_service import PriceService

logger = get_logger("app.services.update_service")


class UpdateService:
    """Serviço para atualização manual de produtos em lotes."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.amazon_client = AmazonClient()
        self.price_service = PriceService(db)

    def update_products(self, products: list[Product]) -> list[dict[str, Any]]:
        """Atualiza uma lista de produtos em lotes de até 10 ASINs."""

        results: list[dict[str, Any]] = []
        for index in range(0, len(products), 10):
            batch = products[index:index + 10]
            asins = [product.asin for product in batch if product.asin]
            if not asins:
                continue

            try:
                response = self.amazon_client.get_items(asins)
            except (ConnectionError, TimeoutError) as exc:
                logger.warning("Erro temporário de rede ao atualizar produtos: %s", exc)
                for product in batch:
                    results.append({"asin": product.asin, "status": "network_error"})
                continue

            items = response.get("itemsResult", {}).get("items", [])
            product_prices_to_record: list[tuple[Product, float]] = []
            for product in batch:
                matched_item = next((item for item in items if item.get("asin") == product.asin), None)
                if not matched_item:
                    results.append({"asin": product.asin, "status": "not_found"})
                    continue

                price = self.amazon_client.extract_price(matched_item)
                if price is None:
                    results.append({"asin": product.asin, "status": "no_price"})
                    continue

                product.title = self.amazon_client.extract_title(matched_item) or product.title
                product.image_url = self.amazon_client.extract_image(matched_item) or product.image_url
                product.affiliate_link = matched_item.get("detailPageURL") or product.affiliate_link
                product_prices_to_record.append((product, price))
                results.append({"asin": product.asin, "status": "updated", "price": price})

            if product_prices_to_record:
                self.price_service.record_prices(product_prices_to_record, commit=True)

        return results
