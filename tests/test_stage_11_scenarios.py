import unittest
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.notification_service import NotificationService
from app.services.price_drop_service import PriceDropService
from app.services.product_service import ProductService
from app.services.update_service import UpdateService


class Stage11ScenariosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_multiple_users_receive_single_notification_for_same_product(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.flush()

        user_a = User(telegram_id="1", username="a")
        user_b = User(telegram_id="2", username="b")
        self.session.add_all([user_a, user_b])
        self.session.flush()

        self.session.add_all([
            UserProduct(user_id=user_a.id, product_id=product.id),
            UserProduct(user_id=user_b.id, product_id=product.id),
        ])
        self.session.commit()

        drop_event = {"previous_price": Decimal("50.00"), "new_price": Decimal("40.00"), "difference": Decimal("10.00"), "percentage": 20.0}
        service = NotificationService(self.session)
        count = service.send_drop_notification(drop_event, product)

        self.assertEqual(count, 2)

    def test_duplicate_products_are_not_created_twice(self) -> None:
        service = ProductService(self.session)
        mocked_response = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Teste"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                    }
                ]
            }
        }
        with patch.object(service.amazon_client, "get_items", return_value=mocked_response):
            first, _ = service.register_product("1", "https://www.amazon.com.br/dp/6528101965")
            second, _ = service.register_product("2", "https://www.amazon.com.br/dp/6528101965")

        self.assertEqual(self.session.query(Product).count(), 1)
        self.assertEqual(first.id, second.id)

    def test_batch_update_processes_products_in_chunks(self) -> None:
        products = [Product(asin=f"ASIN{i}", title=f"Livro {i}") for i in range(12)]
        self.session.add_all(products)
        self.session.commit()

        mocked_response = {
            "itemsResult": {
                "items": [
                    {
                        "asin": f"ASIN{i}",
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": f"Livro {i}"}},
                        "offersV2": {"listings": [{"price": {"amount": 10.0 + i}}]},
                    }
                    for i in range(12)
                ]
            }
        }

        service = UpdateService(self.session)
        with patch.object(service.amazon_client, "get_items", return_value=mocked_response):
            results = service.update_products(products)

        self.assertEqual(len(results), 12)
        self.assertEqual(self.session.query(PriceHistory).count(), 12)

    def test_drop_detection_ignores_non_drop_updates(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        product.price_history = [
            PriceHistory(price=Decimal("40.00")),
            PriceHistory(price=Decimal("45.00")),
        ]

        drop = PriceDropService().detect_drop(product)
        self.assertIsNone(drop)


if __name__ == "__main__":
    unittest.main()
