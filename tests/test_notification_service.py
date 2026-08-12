import unittest
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.notification_service import NotificationService


class NotificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()
        self.service = NotificationService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_send_drop_notification_builds_message_and_counts_recipients(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.flush()

        user = User(telegram_id="1", username="teste")
        self.session.add(user)
        self.session.flush()

        self.session.add(UserProduct(user_id=user.id, product_id=product.id))
        self.session.commit()

        drop_event = {"previous_price": Decimal("50.00"), "new_price": Decimal("40.00"), "difference": Decimal("10.00"), "percentage": 20.0}
        with patch("app.services.notification_service.requests.post") as mock_post:
            mock_post.return_value.content = b'{"ok": true}'
            mock_post.return_value.json.return_value = {"ok": True}
            count = self.service.send_drop_notification(drop_event, product)

        self.assertEqual(count, 1)

    def test_send_drop_notification_skips_users_without_chat_id(self) -> None:
        product = Product(asin="6528101965", title="Livro Teste")
        self.session.add(product)
        self.session.flush()

        user = User(telegram_id="", username="teste")
        self.session.add(user)
        self.session.flush()

        self.session.add(UserProduct(user_id=user.id, product_id=product.id))
        self.session.commit()

        drop_event = {"previous_price": Decimal("50.00"), "new_price": Decimal("40.00"), "difference": Decimal("10.00"), "percentage": 20.0}
        with patch("app.services.notification_service.requests.post") as mock_post:
            mock_post.return_value.content = b'{"ok": true}'
            mock_post.return_value.json.return_value = {"ok": True}
            count = self.service.send_drop_notification(drop_event, product)

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
