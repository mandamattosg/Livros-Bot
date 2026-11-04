import unittest
from unittest.mock import MagicMock, patch

import requests

from app.utils.parse_link import extract_asin


def _resolved_to(url: str) -> MagicMock:
    response = MagicMock()
    response.url = url
    return response


@patch("app.utils.parse_link.requests.get")
class ParseLinkTests(unittest.TestCase):
    def test_extracts_asin_from_standard_amazon_url(self, mock_get: MagicMock) -> None:
        url = "https://www.amazon.com.br/dp/6528101965"
        mock_get.return_value = _resolved_to(url)

        self.assertEqual(extract_asin(url), "6528101965")

    def test_extracts_asin_from_short_amazon_link(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _resolved_to(
            "https://www.amazon.com.br/Livro-Exemplo/dp/6555653302?ref=short"
        )

        self.assertEqual(extract_asin("https://link.amazon/B0apZ6FEa"), "6555653302")
        mock_get.assert_called_once_with("https://link.amazon/B0apZ6FEa", allow_redirects=True, timeout=10)

    def test_short_link_code_is_not_treated_as_asin_when_resolution_fails(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.ConnectionError("sem rede")

        self.assertIsNone(extract_asin("https://link.amazon/B0apZ6FEa"))

    def test_standard_url_still_works_when_resolution_fails(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.ConnectionError("sem rede")

        self.assertEqual(extract_asin("https://www.amazon.com.br/dp/6528101965"), "6528101965")

    def test_rejects_non_amazon_domain(self, mock_get: MagicMock) -> None:
        url = "https://example.com/product/6528101965"
        mock_get.return_value = _resolved_to(url)

        self.assertIsNone(extract_asin(url))


if __name__ == "__main__":
    unittest.main()
