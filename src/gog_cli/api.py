"""GOG API client and TokenStore protocol."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import requests

from gog_cli import log
from gog_cli.errors import AuthError, NetworkError

_log = log.get_logger(__name__)

_CLIENT_ID = "46899977096215655"
_CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"  # noqa: S105 - Public GOG Galaxy OAuth client credential.
_TOKEN_URL = "https://auth.gog.com/token"  # noqa: S105 - URL constant, not a secret.

_OWNED_GAMES_URL = "https://embed.gog.com/user/data/games"
_LIBRARY_URL = "https://embed.gog.com/account/getFilteredProducts"
_PRODUCT_URL = "https://api.gog.com/products/{product_id}"
# Unofficial public catalog search endpoint — no authentication required.
_CATALOG_SEARCH_URL = "https://catalog.gog.com/v1/catalog"


class TokenStore(Protocol):
    def load_tokens(self) -> dict:
        """Return stored tokens: {"access_token": str, "refresh_token": str, "expires_at": str}"""
        ...

    def save_tokens(self, tokens: dict) -> None:
        """Persist updated tokens after a refresh."""
        ...


class GogApiClient:
    def __init__(self, token_store: TokenStore) -> None:
        self._token_store = token_store
        self._session = requests.Session()

    def _access_token(self) -> str:
        return self._token_store.load_tokens()["access_token"]

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def _refresh_tokens(self) -> None:
        tokens = self._token_store.load_tokens()
        try:
            resp = self._session.get(
                _TOKEN_URL,
                params={
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise AuthError(f"token refresh failed: {exc}") from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise AuthError(f"token refresh network error: {exc}") from exc

        data = resp.json()
        expires_at = datetime.fromtimestamp(
            datetime.now(tz=UTC).timestamp() + data["expires_in"],
            tz=UTC,
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self._token_store.save_tokens(
            {
                **tokens,
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": expires_at,
            }
        )

    def _get(self, url: str, **kwargs: object) -> requests.Response:
        try:
            resp = self._session.get(url, headers=self._auth_headers(), timeout=30, **kwargs)
        except (requests.ConnectionError, requests.Timeout, ConnectionError) as exc:
            raise NetworkError(f"network error: {exc}") from exc

        if resp.status_code == 401:
            self._refresh_tokens()
            try:
                resp = self._session.get(
                    url, headers=self._auth_headers(), timeout=30, **kwargs
                )
            except (requests.ConnectionError, requests.Timeout, ConnectionError) as exc:
                raise NetworkError(f"network error: {exc}") from exc
            if resp.status_code == 401:
                raise AuthError("authentication failed after token refresh")

        if not resp.ok:
            raise NetworkError(f"HTTP {resp.status_code}: {log.redact(url)}")

        return resp

    def get_owned_ids(self) -> list[int]:
        resp = self._get(_OWNED_GAMES_URL)
        return resp.json()["owned"]

    def get_library_page(self, page: int) -> dict:
        resp = self._get(_LIBRARY_URL, params={"mediaType": 1, "page": page})
        return resp.json()

    def get_product_downloads(self, product_id: int) -> dict:
        url = _PRODUCT_URL.format(product_id=product_id)
        resp = self._get(url, params={"expand": "downloads"})
        return resp.json()

    def resolve_downlink_url(self, downlink_url: str) -> tuple[str, str]:
        resp = self._get(downlink_url)
        data = resp.json()
        return data["downlink"], data.get("checksum", "")


def search_catalog(query: str, *, page: int = 1) -> dict:
    """Search the public GOG catalog without authentication.

    Uses an unofficial reverse-engineered endpoint; no stability guarantees.
    """
    try:
        resp = requests.get(
            _CATALOG_SEARCH_URL,
            params={
                "search": query,
                "limit": 48,
                "page": page,
                "order": "desc:relevance",
                "productType": "in:game",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise NetworkError(f"catalog search failed: {exc}") from exc
    except (requests.ConnectionError, requests.Timeout, ConnectionError) as exc:
        raise NetworkError(f"catalog search network error: {exc}") from exc
    return resp.json()
