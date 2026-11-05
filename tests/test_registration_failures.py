import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.base import Base
from app.models.product import Product
from app.models.registration_failure import (
    AMAZON_ERROR,
    INVALID_LINK,
    LIMIT_REACHED,
    LINK_NOT_AT_START,
    PRODUCT_NOT_FOUND,
    RegistrationFailure,
)
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.admin_report_service import build_admin_report_message, get_registration_failure_stats
from app.services.product_service import ProductService
from app.services.registration_failure_service import record_registration_failure
from app.utils.datetime_utc import utc_now

VALID_LINK = "https://www.amazon.com.br/dp/6528101965"
FOUND_ITEMS = {
    "itemsResult": {
        "items": [
            {
                "detailPageURL": VALID_LINK,
                "itemInfo": {"title": {"displayValue": "Livro Teste"}},
                "images": {"primary": {"large": {"url": "https://img.test"}}},
            }
        ]
    }
}


@patch("app.utils.parse_link.requests.get", side_effect=requests.ConnectionError("sem rede"))
class RegistrationFailureRecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.service = ProductService(self.session)
        self.user = self.service.get_or_create_user("123")

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def _failures(self) -> list[RegistrationFailure]:
        return self.session.query(RegistrationFailure).all()

    def test_records_invalid_link(self, _get: MagicMock) -> None:
        product, _ = self.service.register_product("123", "https://example.com/livro")

        self.assertIsNone(product)
        [failure] = self._failures()
        self.assertEqual(failure.reason, INVALID_LINK)
        self.assertEqual(failure.user_id, self.user.id)
        self.assertEqual(failure.link, "https://example.com/livro")

    def test_records_amazon_error_with_detail(self, _get: MagicMock) -> None:
        with patch.object(self.service.amazon_client, "get_items", side_effect=RuntimeError("429 Too Many Requests")):
            self.service.register_product("123", VALID_LINK)

        [failure] = self._failures()
        self.assertEqual(failure.reason, AMAZON_ERROR)
        self.assertIn("429", failure.detail)

    def test_records_product_not_found(self, _get: MagicMock) -> None:
        with patch.object(self.service.amazon_client, "get_items", return_value={"itemsResult": {"items": []}}):
            self.service.register_product("123", VALID_LINK)

        [failure] = self._failures()
        self.assertEqual(failure.reason, PRODUCT_NOT_FOUND)

    def test_records_limit_reached(self, _get: MagicMock) -> None:
        with patch.object(settings, "USER_PRODUCT_MONITOR_LIMIT", 1), patch.object(
            self.service.amazon_client, "get_items", return_value=FOUND_ITEMS
        ):
            self.service.register_product("123", VALID_LINK)
            product, _ = self.service.register_product("123", "https://www.amazon.com.br/dp/6528101966")

        self.assertIsNone(product)
        [failure] = self._failures()
        self.assertEqual(failure.reason, LIMIT_REACHED)

    def test_successful_registration_records_nothing(self, _get: MagicMock) -> None:
        with patch.object(self.service.amazon_client, "get_items", return_value=FOUND_ITEMS):
            product, _ = self.service.register_product("123", VALID_LINK)

        self.assertIsNotNone(product)
        self.assertEqual(self._failures(), [])

    def test_recording_never_raises(self, _get: MagicMock) -> None:
        with patch.object(self.session, "commit", side_effect=RuntimeError("banco fora")):
            record_registration_failure(self.session, "123", INVALID_LINK)


class RegistrationFailureReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_stats_count_recent_failures_and_unrecovered_users(self) -> None:
        gave_up = User(telegram_id="1")
        recovered = User(telegram_id="2")
        product = Product(asin="6528101965", title="Livro")
        self.session.add_all([gave_up, recovered, product])
        self.session.flush()
        self.session.add(UserProduct(user_id=recovered.id, product_id=product.id))
        self.session.add_all([
            RegistrationFailure(user_id=gave_up.id, reason=LINK_NOT_AT_START),
            RegistrationFailure(user_id=gave_up.id, reason=LINK_NOT_AT_START),
            RegistrationFailure(user_id=recovered.id, reason=INVALID_LINK),
            RegistrationFailure(
                user_id=gave_up.id,
                reason=AMAZON_ERROR,
                created_at=utc_now() - timedelta(days=30),
            ),
        ])
        self.session.commit()

        stats = get_registration_failure_stats(self.session)

        self.assertEqual(stats["registration_failures"], 3)
        self.assertEqual(stats["registration_failures_by_reason"], {LINK_NOT_AT_START: 2, INVALID_LINK: 1})
        self.assertEqual(stats["registration_failure_users_without_product"], 1)

    def test_message_shows_breakdown_only_when_there_are_failures(self) -> None:
        with_failures = build_admin_report_message({
            "registration_failures": 3,
            "registration_failures_by_reason": {LINK_NOT_AT_START: 2, INVALID_LINK: 1},
            "registration_failure_users_without_product": 1,
        })
        without_failures = build_admin_report_message({"registration_failures": 0})

        self.assertIn("Cadastros com falha (7 dias): 3", with_failures)
        self.assertIn("Link no meio do texto: 2", with_failures)
        self.assertIn("Link inválido: 1", with_failures)
        self.assertIn("seguem sem livro: 1", with_failures)
        self.assertIn("Cadastros com falha (7 dias): 0", without_failures)
        self.assertNotIn("seguem sem livro", without_failures)


class HandleTextLinkPositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)

    def _send(self, text: str) -> None:
        import asyncio

        from app.bot import telegram_bot

        update = MagicMock()
        update.message.text = text
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        with patch.object(telegram_bot, "SessionLocal", self.Session):
            asyncio.run(telegram_bot.handle_text(update, MagicMock()))

    def _reasons(self) -> list[str]:
        with self.Session() as session:
            return [failure.reason for failure in session.query(RegistrationFailure).all()]

    def test_records_shared_text_with_link_in_the_middle(self) -> None:
        self._send("Confira este produto na Amazon! https://a.co/d/abc123")

        self.assertEqual(self._reasons(), [LINK_NOT_AT_START])

    def test_ignores_plain_text_without_link(self) -> None:
        self._send("oi, tudo bem?")

        self.assertEqual(self._reasons(), [])


if __name__ == "__main__":
    unittest.main()
