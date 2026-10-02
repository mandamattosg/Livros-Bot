from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def build_affiliate_link(
    affiliate_link: str | None,
    asin: str | None,
    partner_tag: str | None,
    *,
    fallback_to_product_url: bool,
) -> str | None:
    """Return the saved product URL with the current partner tag applied."""

    link = (affiliate_link or "").strip()
    tag = (partner_tag or "").strip()

    if not link:
        if not asin:
            return None
        if not tag and not fallback_to_product_url:
            return None
        link = f"https://www.amazon.com.br/dp/{asin}"

    if not tag:
        return link

    parsed = urlsplit(link)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "tag"]
    query.append(("tag", tag))
    return urlunsplit(parsed._replace(query=urlencode(query)))