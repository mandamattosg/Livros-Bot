import unittest
from decimal import Decimal

from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.price_drop_service import PriceDropService


class PriceDropServiceTests(unittest.TestCase):
    def test_detect_drop_returns_event_when_price_falls(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        product.price_history = [
            PriceHistory(price=Decimal("50.00")),
            PriceHistory(price=Decimal("46.00")),
        ]

        drop = PriceDropService().detect_drop(product)

        self.assertIsNotNone(drop)
        self.assertEqual(drop["previous_price"], Decimal("50.00"))
        self.assertEqual(drop["new_price"], Decimal("46.00"))
        self.assertEqual(drop["difference"], Decimal("4.00"))

    def test_detect_drop_returns_none_when_difference_is_below_minimum(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        product.price_history = [
            PriceHistory(price=Decimal("50.00")),
            PriceHistory(price=Decimal("48.00")),
        ]

        drop = PriceDropService().detect_drop(product)

        self.assertIsNone(drop)

    def test_detect_drop_returns_none_when_price_does_not_fall(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        product.price_history = [
            PriceHistory(price=Decimal("40.00")),
            PriceHistory(price=Decimal("45.00")),
        ]

        drop = PriceDropService().detect_drop(product)

        self.assertIsNone(drop)


if __name__ == "__main__":
    unittest.main()
