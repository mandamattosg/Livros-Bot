import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from app.amazon import client as amazon_client_module
from app.amazon.client import AmazonClient


class StubResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._json_data


class AmazonClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.client = AmazonClient()
        self.cache_file = Path(self.temp_dir.name) / "amazon_oauth_cache.json"
        self.client._token_cache_file = self.cache_file

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_uses_env_token_without_network_call(self) -> None:
        self.client.session.post = Mock()

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", "env-token", create=True):
            with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_ID", None, create=True):
                with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_SECRET", None, create=True):
                    token = self.client.get_access_token()

        self.assertEqual(token, "env-token")
        self.client.session.post.assert_not_called()

    def test_caches_oauth_token_between_calls(self) -> None:
        self.client.session.post = Mock(return_value=StubResponse(200, {"access_token": "oauth-token", "expires_in": 3600}))

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", None, create=True):
            first = self.client.get_access_token()
            second = self.client.get_access_token()

        self.assertEqual(first, "oauth-token")
        self.assertEqual(second, "oauth-token")
        self.assertEqual(self.client.session.post.call_count, 1)

    def test_loads_persisted_oauth_token_without_network_call(self) -> None:
        self.cache_file.write_text('{"access_token": "persisted-token", "expires_at": 4102444800}', encoding="utf-8")
        self.client.session.post = Mock()

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", None, create=True):
            with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_ID", "client-id", create=True):
                with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_SECRET", "client-secret", create=True):
                    token = self.client.get_access_token()

        self.assertEqual(token, "persisted-token")
        self.client.session.post.assert_not_called()

    def test_prefers_oauth_over_legacy_manual_token_when_client_credentials_exist(self) -> None:
        self.client.session.post = Mock(return_value=StubResponse(200, {"access_token": "oauth-token", "expires_in": 3600}))

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", None, create=True):
            with patch.object(amazon_client_module.settings, "AMAZON_LEGACY_ACCESS_TOKEN", "legacy-token", create=True):
                with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_ID", "client-id", create=True):
                    with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_SECRET", "client-secret", create=True):
                        token = self.client.get_access_token()

        self.assertEqual(token, "oauth-token")
        self.assertEqual(self.client.session.post.call_count, 1)

    def test_retries_on_transient_server_error(self) -> None:
        self.client.session.post = Mock(
            side_effect=[
                StubResponse(500, {}),
                StubResponse(200, {"access_token": "retried-token", "expires_in": 3600}),
            ]
        )

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", None, create=True):
            token = self.client.get_access_token()

        self.assertEqual(token, "retried-token")
        self.assertEqual(self.client.session.post.call_count, 2)

    def test_requests_oauth_token_with_form_urlencoded_body(self) -> None:
        self.client.session.post = Mock(return_value=StubResponse(200, {"access_token": "oauth-token", "expires_in": 3600}))

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", None, create=True):
            with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_ID", "client-id", create=True):
                with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_SECRET", "client-secret", create=True):
                    token = self.client.get_access_token()

        self.assertEqual(token, "oauth-token")
        kwargs = self.client.session.post.call_args.kwargs
        self.assertEqual(kwargs.get("data"), {
            "grant_type": "client_credentials",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scope": "creatorsapi::default",
        })
        self.assertNotIn("json", kwargs)

    def test_persists_oauth_token_after_fetch(self) -> None:
        self.client.session.post = Mock(return_value=StubResponse(200, {"access_token": "oauth-token", "expires_in": 3600}))

        with patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", None, create=True):
            with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_ID", "client-id", create=True):
                with patch.object(amazon_client_module.settings, "AMAZON_CLIENT_SECRET", "client-secret", create=True):
                    self.client.get_access_token()

        self.assertTrue(self.cache_file.exists())
        self.assertIn("oauth-token", self.cache_file.read_text(encoding="utf-8"))

    def test_extract_price_from_nested_money_structure(self) -> None:
        item = {
            "offersV2": {
                "listings": [
                    {
                        "price": {
                            "money": {
                                "amount": 44.85,
                                "currency": "BRL",
                            }
                        }
                    }
                ]
            }
        }

        price = self.client.extract_price(item)

        self.assertEqual(price, 44.85)

    def test_records_each_creators_api_attempt_including_429_retries(self) -> None:
        self.client.session.post = Mock(return_value=StubResponse(429, {}))

        with (
            patch.object(amazon_client_module.settings, "AMAZON_ACCESS_TOKEN", "test-token", create=True),
            patch.object(amazon_client_module.settings, "AMAZON_CLIENT_ID", None, create=True),
            patch.object(amazon_client_module.settings, "AMAZON_CLIENT_SECRET", None, create=True),
            patch("app.amazon.client.record_creator_api_request") as record_request,
            patch("app.amazon.client.time.sleep"),
        ):
            with self.assertRaises(amazon_client_module.AmazonRateLimitError):
                self.client.get_items(["B000000001"])

        self.assertEqual(self.client.session.post.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in record_request.call_args_list],
            [429, 429, 429],
        )


if __name__ == "__main__":
    unittest.main()
