import unittest

from app.utils.parse_link import extract_asin


class ParseLinkTests(unittest.TestCase):
    def test_extracts_asin_from_standard_amazon_url(self) -> None:
        self.assertEqual(extract_asin("https://www.amazon.com.br/dp/6528101965"), "6528101965")

    def test_extracts_asin_from_short_amazon_link(self) -> None:
        self.assertEqual(extract_asin("https://link.amazon/B0apZ6FEa"), "6555653302")


if __name__ == "__main__":
    unittest.main()
