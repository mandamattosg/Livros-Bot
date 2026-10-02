from __future__ import annotations

from unittest.mock import patch

from app.services.admin_alert_service import send_admin_alert


def test_send_admin_alert_returns_true_when_telegram_accepts_message() -> None:
    with (
        patch("app.services.admin_alert_service.settings.ADMIN_ALERTS_ENABLED", True),
        patch("app.services.admin_alert_service.settings.TELEGRAM_BOT_TOKEN", "token"),
        patch("app.services.admin_alert_service.settings.ADMIN_ALERT_CHAT_ID", "123"),
        patch("app.services.admin_alert_service.requests.post") as post,
    ):
        post.return_value.content = b'{"ok": true}'
        post.return_value.json.return_value = {"ok": True}
        assert send_admin_alert("report")


def test_send_admin_alert_returns_false_when_telegram_rejects_message() -> None:
    with (
        patch("app.services.admin_alert_service.settings.ADMIN_ALERTS_ENABLED", True),
        patch("app.services.admin_alert_service.settings.TELEGRAM_BOT_TOKEN", "token"),
        patch("app.services.admin_alert_service.settings.ADMIN_ALERT_CHAT_ID", "123"),
        patch("app.services.admin_alert_service.requests.post") as post,
    ):
        post.return_value.content = b'{"ok": false, "description": "chat not found"}'
        post.return_value.json.return_value = {"ok": False, "description": "chat not found"}
        assert not send_admin_alert("report")
