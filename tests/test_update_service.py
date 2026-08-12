import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.update_service import UpdateService


class UpdateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()
        self.service = UpdateService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_update_products_groups_by_batch_and_records_history(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)

        mocked_response = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "6528101965",
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Atualizado"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"amount": 29.90}}]},
                    }
                ]
            }
        }

        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_response):
            results = self.service.update_products([product])

        self.assertEqual(results[0]["status"], "updated")
        self.assertEqual(results[0]["price"], 29.90)
        self.assertEqual(self.session.query(PriceHistory).count(), 1)


if __name__ == "__main__":
    unittest.main()
