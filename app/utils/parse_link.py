from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import requests

BOOK_CATEGORIES = {"books", "kindle-store", "audible"}


def _extract_from_text(text: str) -> str | None:
    candidates: list[str] = []

    if text:
        path_parts = [part for part in text.split("/") if part]
        if path_parts:
            candidates.append(path_parts[-1])
            if len(path_parts) >= 2:
                candidates.append(path_parts[-2])
            if len(path_parts) >= 1:
                candidates.append(path_parts[0])

    for candidate in candidates:
        match = re.fullmatch(r"[A-Za-z0-9]{10}", candidate)
        if match:
            return candidate.upper()

    match = re.search(r"/([A-Za-z0-9]{10})(?:/|$)", text)
    if match:
        return match.group(1).upper()

    return None


def is_book_link(url: str) -> bool:
    """Retorna True quando a URL aponta para uma página de livro na Amazon."""

    if not url:
        return False

    normalized = url.strip()
    if not normalized:
        return False

    try:
        response = requests.get(normalized, allow_redirects=True, timeout=10)
        final_url = response.url
    except requests.RequestException:
        final_url = normalized

    parsed = urlparse(final_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return False

    category = path_parts[0].lower()
    return category in BOOK_CATEGORIES


def extract_asin(url: str) -> str | None:
    """Extrai o ASIN de URLs da Amazon em formatos comuns, incluindo links curtos."""

    if not url:
        return None

    normalized = url.strip()
    if not normalized:
        return None

    try:
        response = requests.get(normalized, allow_redirects=True, timeout=10)
        final_url = response.url
    except requests.RequestException:
        final_url = normalized

    parsed = urlparse(final_url)
    host = parsed.netloc.lower()

    if not any(host.endswith(domain) for domain in ("amazon.com", "amazon.com.br", "www.amazon.com", "www.amazon.com.br", "link.amazon")):
        return None

    path = parsed.path or ""
    if path and path != "/":
        path_candidate = path.strip("/")
        if path_candidate and re.fullmatch(r"[A-Za-z0-9]{10}", path_candidate):
            return path_candidate.upper()

    asins = [
        _extract_from_text(parsed.path),
        _extract_from_text(parsed.netloc),
    ]

    query_params = parse_qs(parsed.query)
    if "tag" in query_params:
        asins.append(_extract_from_text(query_params["tag"][0]))

    for asin in asins:
        if asin:
            return asin

    return None
