import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    from app.bot.telegram_bot import (
        build_help_message,
        build_product_affiliate_link,
        build_removal_keyboard,
        build_status_keyboard,
        is_admin_user,
    )
    TELEGRAM_BOT_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover
    TELEGRAM_BOT_IMPORT_ERROR = exc


@unittest.skipIf(TELEGRAM_BOT_IMPORT_ERROR is not None, "python-telegram-bot não está instalado neste ambiente")
class TelegramBotTests(unittest.TestCase):
    def test_build_help_message_mentions_livro_and_remover(self) -> None:
        message = build_help_message()

        self.assertIn("/livro", message)
        self.assertIn("/remover", message)
        self.assertIn("/ajuda", message)

    def test_build_help_message_for_admin_mentions_relatorio(self) -> None:
        message = build_help_message(is_admin=True)

        self.assertIn("/relatorio", message)

    def test_is_admin_user_checks_admin_telegram_id(self) -> None:
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123))
        with patch("app.bot.telegram_bot.settings.ADMIN_TELEGRAM_ID", "123"):
            self.assertTrue(is_admin_user(update))

        with patch("app.bot.telegram_bot.settings.ADMIN_TELEGRAM_ID", "999"):
            self.assertFalse(is_admin_user(update))

    def test_build_removal_keyboard_uses_callback_data(self) -> None:
        products = [
            SimpleNamespace(id=1, title="Livro 1"),
            SimpleNamespace(id=2, title="Livro 2"),
        ]

        keyboard = build_removal_keyboard(products)

        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "remove:1")
        self.assertEqual(keyboard.inline_keyboard[1][0].callback_data, "remove:2")

    def test_build_status_keyboard_uses_callback_data(self) -> None:
        products = [
            SimpleNamespace(id=1, title="Livro 1"),
            SimpleNamespace(id=2, title="Livro 2"),
        ]

        keyboard = build_status_keyboard(products)

        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "status:1")
        self.assertEqual(keyboard.inline_keyboard[1][0].callback_data, "status:2")

    def test_build_product_affiliate_link_uses_product_link(self) -> None:
        product = SimpleNamespace(asin="123", affiliate_link="https://example.com/product")

        with patch("app.bot.telegram_bot.settings.AMAZON_PARTNER_TAG", None):
            link = build_product_affiliate_link(product)

        self.assertEqual(link, "https://example.com/product")

    def test_build_product_affiliate_link_replaces_stored_partner_tag(self) -> None:
        product = SimpleNamespace(
            asin="123",
            affiliate_link="https://www.amazon.com.br/dp/123?tag=old-tag&ref_=abc",
        )

        with patch("app.bot.telegram_bot.settings.AMAZON_PARTNER_TAG", "new-tag-20"):
            link = build_product_affiliate_link(product)

        self.assertEqual(link, "https://www.amazon.com.br/dp/123?ref_=abc&tag=new-tag-20")


if __name__ == "__main__":
    unittest.main()
