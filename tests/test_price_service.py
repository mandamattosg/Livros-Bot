import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.price_service import PriceService


class PriceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()
        self.service = PriceService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_record_price_creates_history_entry(self) -> None:
        product = Product(asin="1234567890", title="Livro Teste")
        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)

        entry = self.service.record_price(product, 19.99)

        self.assertIsInstance(entry, PriceHistory)
        self.assertEqual(entry.product_id, product.id)
        self.assertEqual(entry.price, Decimal("19.99"))
        self.assertEqual(self.session.query(PriceHistory).count(), 1)

    def test_record_prices_creates_entries_in_bulk(self) -> None:
        first = Product(asin="1234567890", title="Livro Teste 1")
        second = Product(asin="0987654321", title="Livro Teste 2")
        self.session.add_all([first, second])
        self.session.commit()
        self.session.refresh(first)
        self.session.refresh(second)

        entries = self.service.record_prices([(first, 19.99), (second, "21.50")])

        self.assertEqual(len(entries), 2)
        prices = [entry.price for entry in self.session.query(PriceHistory).order_by(PriceHistory.id.asc()).all()]
        self.assertEqual(prices, [Decimal("19.99"), Decimal("21.50")])


if __name__ == "__main__":
    unittest.main()
