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


def test_send_admin_alert_logs_telegram_rejection_without_sensitive_url() -> None:
    with (
        patch("app.services.admin_alert_service.settings.ADMIN_ALERTS_ENABLED", True),
        patch("app.services.admin_alert_service.settings.TELEGRAM_BOT_TOKEN", "secret-token"),
        patch("app.services.admin_alert_service.settings.ADMIN_ALERT_CHAT_ID", "123"),
        patch("app.services.admin_alert_service.requests.post") as post,
        patch("app.services.admin_alert_service.logger.warning") as warning,
    ):
        post.return_value.ok = False
        post.return_value.status_code = 400
        post.return_value.content = b'{"ok": false, "description": "chat not found"}'
        post.return_value.json.return_value = {"ok": False, "description": "chat not found"}

        assert not send_admin_alert("report")

    warning.assert_called_once()
    assert "chat not found" in warning.call_args.args[2]
    assert "secret-token" not in str(warning.call_args)


def test_send_admin_alert_logs_missing_environment_values() -> None:
    with (
        patch("app.services.admin_alert_service.settings.ADMIN_ALERTS_ENABLED", True),
        patch("app.services.admin_alert_service.settings.TELEGRAM_BOT_TOKEN", None),
        patch("app.services.admin_alert_service.settings.ADMIN_ALERT_CHAT_ID", None),
        patch("app.services.admin_alert_service.settings.ADMIN_TELEGRAM_ID", None),
        patch("app.services.admin_alert_service.logger.warning") as warning,
    ):
        assert not send_admin_alert("report")

    warning.assert_called_once()
    assert "TELEGRAM_BOT_TOKEN" in warning.call_args.args[0]
