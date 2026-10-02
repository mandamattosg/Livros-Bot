from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from app.config import settings
from app.logging import get_logger
from app.amazon.usage import record_creator_api_request


class AmazonClientError(Exception):
    """Erro base para falhas na integração com a Amazon."""


class AmazonAuthenticationError(AmazonClientError):
    """Erro para falhas de autenticação ou credenciais inválidas."""


class AmazonRateLimitError(AmazonClientError):
    """Erro para quando a API responde com throttling."""


class AmazonClient:
    """Cliente resiliente para integração com a Creators API da Amazon."""

    def __init__(self) -> None:
        self.logger = get_logger("app.amazon.client")
        self.base_url = "https://creatorsapi.amazon/catalog/v1/getItems"
        self.session = requests.Session()
        self._access_token: str | None = None
        self._token_expires_at: float | None = None
        self._token_cache_file = Path(settings.AMAZON_TOKEN_CACHE_FILE)

    def _validate_credentials(self) -> None:
        if self._get_static_token():
            return

        if not settings.AMAZON_CLIENT_ID or not settings.AMAZON_CLIENT_SECRET:
            raise AmazonAuthenticationError("Credenciais da Amazon ausentes. Configure AMAZON_CLIENT_ID e AMAZON_CLIENT_SECRET ou AMAZON_ACCESS_TOKEN.")

    def _get_static_token(self) -> str | None:
        explicit_token = (settings.AMAZON_ACCESS_TOKEN or "").strip()
        if explicit_token:
            return explicit_token

        # Compatibilidade com a configuração antiga. Se as credenciais OAuth estiverem
        # configuradas, preferimos renovação automática em vez de um token manual.
        if settings.AMAZON_CLIENT_ID and settings.AMAZON_CLIENT_SECRET:
            return None

        legacy_token = (settings.AMAZON_LEGACY_ACCESS_TOKEN or "").strip()
        return legacy_token or None

    def _get_cached_token(self) -> str | None:
        if not self._access_token:
            return None
        if self._token_expires_at and time.time() >= self._token_expires_at:
            self._access_token = None
            self._token_expires_at = None
            return None
        return self._access_token

    def _load_persisted_token(self) -> str | None:
        if not self._token_cache_file.exists():
            return None

        try:
            payload = json.loads(self._token_cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.logger.warning("Não foi possível ler o cache OAuth da Amazon: %s", exc)
            return None

        token = payload.get("access_token")
        expires_at = payload.get("expires_at")
        if not token or not isinstance(expires_at, (int, float)):
            return None

        if time.time() >= float(expires_at):
            return None

        self._access_token = str(token)
        self._token_expires_at = float(expires_at)
        return self._access_token

    def _persist_token(self, token: str, expires_at: float | None) -> None:
        if expires_at is None:
            return

        payload = {"access_token": token, "expires_at": expires_at}
        try:
            self._token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._token_cache_file.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as exc:
            self.logger.warning("Não foi possível persistir o cache OAuth da Amazon: %s", exc)

    def _clear_persisted_token(self) -> None:
        self._access_token = None
        self._token_expires_at = None
        try:
            if self._token_cache_file.exists():
                self._token_cache_file.unlink()
        except OSError as exc:
            self.logger.warning("Não foi possível limpar o cache OAuth da Amazon: %s", exc)

    def _fetch_oauth_token(self) -> str:
        self._validate_credentials()

        url = "https://api.amazon.com/auth/o2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.AMAZON_CLIENT_ID,
            "client_secret": settings.AMAZON_CLIENT_SECRET,
            "scope": "creatorsapi::default",
        }

        for attempt in range(3):
            try:
                response = self.session.post(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30,
                )
                if response.status_code == 401:
                    raise AmazonAuthenticationError("Falha de autenticação ao obter token da Amazon")
                if response.status_code == 429:
                    raise AmazonRateLimitError("Limite de requisições da Amazon atingido")
                if response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                data = response.json()
                token = data.get("access_token")
                if not token:
                    raise AmazonAuthenticationError("Token de acesso não retornado pela API da Amazon")

                expires_in = data.get("expires_in")
                self._token_expires_at = None
                if isinstance(expires_in, (int, float)):
                    self._token_expires_at = time.time() + float(expires_in) - 60
                self._access_token = token
                self._persist_token(token, self._token_expires_at)
                return token
            except (requests.RequestException, AmazonAuthenticationError, AmazonRateLimitError) as exc:
                if attempt == 2:
                    raise
                self.logger.warning("Falha ao obter token da Amazon. Tentando novamente em %ss. Erro: %s", 2 ** attempt, exc)
                time.sleep(2 ** attempt)

        raise AmazonAuthenticationError("Não foi possível obter um token da Amazon")

    def get_access_token(self) -> str:
        """Obtém um token para a Creators API, priorizando um token já configurado no ambiente e reutilizando o cache."""

        cached = self._get_cached_token()
        if cached:
            return cached

        persisted = self._load_persisted_token()
        if persisted:
            return persisted

        if settings.AMAZON_CLIENT_ID and settings.AMAZON_CLIENT_SECRET:
            return self._fetch_oauth_token()

        static_token = self._get_static_token()
        if static_token:
            self._access_token = static_token
            self._token_expires_at = None
            return self._access_token

        self._validate_credentials()
        raise AmazonAuthenticationError("Não foi possível obter um token da Amazon")

    def get_items(self, asins: list[str]) -> dict[str, Any]:
        """Consulta a Creators API para uma lista de ASINs com retry e tratamento de erros."""

        if not asins:
            return {"itemsResult": {"items": []}}

        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-marketplace": settings.AMAZON_MARKETPLACE,
        }
        payload = {
            "itemIds": asins,
            "partnerTag": settings.AMAZON_PARTNER_TAG,
            "partnerType": "Associates",
            "resources": [
                "itemInfo.title",
                "itemInfo.externalIds",
                "browseNodeInfo.browseNodes",
                "browseNodeInfo.browseNodes.ancestor",
                "offersV2.listings.price",
                "images.primary.large",
            ],
        }

        for attempt in range(3):
            response = None
            request_started = False
            try:
                token = self.get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                request_started = True
                response = self.session.post(self.base_url, headers=headers, json=payload, timeout=30)
                record_creator_api_request(response.status_code)
                if response.status_code == 401:
                    self._clear_persisted_token()
                    raise AmazonAuthenticationError("Falha de autenticação ao consultar a Creators API")
                if response.status_code == 429:
                    raise AmazonRateLimitError("Limite de requisições para a Creators API atingido")
                if response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, AmazonRateLimitError, AmazonAuthenticationError) as exc:
                if request_started and response is None:
                    record_creator_api_request(None)
                if attempt == 2:
                    raise
                self.logger.warning("Falha na consulta à Creators API. Tentando novamente em %ss. Erro: %s", 2 ** attempt, exc)
                time.sleep(2 ** attempt)

        raise AmazonClientError("Não foi possível consultar a Creators API")

    def extract_title(self, item: dict) -> str | None:
        """Extrai o título do item a partir da resposta da API."""

        item_info = item.get("itemInfo", {})
        title = item_info.get("title")
        if not title:
            return None
        return title.get("displayValue") or title.get("value")

    def extract_price(self, item: dict) -> float | None:
        """Extrai o preço do item a partir da resposta da API."""

        offers = item.get("offersV2", {}).get("listings", [])
        if not offers:
            return None

        first_offer = offers[0]
        price = first_offer.get("price")
        if not price:
            return None

        money = price.get("money") or {}
        amount = price.get("amount")
        currency = price.get("currency")

        if amount is None:
            amount = money.get("amount")

        if currency is None:
            currency = money.get("currency")

        if amount is None:
            return None

        if currency and currency.upper() != "BRL":
            self.logger.warning("Moeda não suportada para conversão: %s", currency)

        return float(amount)

    def extract_image(self, item: dict) -> str | None:
        """Extrai a URL da imagem principal do item."""

        images = item.get("images", {})
        primary = images.get("primary", {})
        large = primary.get("large")
        if not large:
            return None
        return large.get("url")

    def extract_browse_nodes(self, item: dict) -> list[str]:
        """Extrai os nomes dos browse nodes do item, incluindo ancestrais."""

        browse_nodes: list[str] = []
        browse_node_info = item.get("browseNodeInfo")
        if not isinstance(browse_node_info, dict):
            browse_node_info = item.get("itemInfo", {}).get("browseNodeInfo", {})
        if not isinstance(browse_node_info, dict):
            return browse_nodes

        nodes = browse_node_info.get("browseNodes", [])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            name = node.get("displayName") or node.get("name")
            if name:
                browse_nodes.append(str(name))
            ancestors = node.get("ancestor") or []
            if isinstance(ancestors, list):
                for ancestor in ancestors:
                    if isinstance(ancestor, dict):
                        ancestor_name = ancestor.get("displayName") or ancestor.get("name")
                        if ancestor_name:
                            browse_nodes.append(str(ancestor_name))

        return browse_nodes

    def extract_external_ids(self, item: dict) -> list[str]:
        """Extrai IDs externos como ISBN-10/ISBN-13 do item."""

        external_ids: list[str] = []
        external_ids_info = item.get("itemInfo", {}).get("externalIds", {})
        if isinstance(external_ids_info, dict):
            for key in ("ISBN10", "ISBN13"):
                value = external_ids_info.get(key)
                if isinstance(value, dict):
                    identifier = value.get("value") or value.get("displayValue")
                    if identifier:
                        external_ids.append(str(identifier))
                elif isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, dict):
                            identifier = entry.get("value") or entry.get("displayValue")
                            if identifier:
                                external_ids.append(str(identifier))
                        elif entry:
                            external_ids.append(str(entry))
                elif value:
                    external_ids.append(str(value))
        elif isinstance(external_ids_info, list):
            for entry in external_ids_info:
                if isinstance(entry, dict):
                    identifier = entry.get("value") or entry.get("displayValue")
                    if identifier:
                        external_ids.append(str(identifier))

        return external_ids
