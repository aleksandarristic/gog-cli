"""Tests for gog_cli.api — GogApiClient and TokenStore protocol."""

from __future__ import annotations

import pytest
import responses as rsps_lib

from gog_cli.api import GogApiClient, TokenStore
from gog_cli.errors import AuthError, NetworkError

_TOKEN_URL = "https://auth.gog.com/token"
_OWNED_URL = "https://embed.gog.com/user/data/games"
_LIBRARY_URL = "https://embed.gog.com/account/getFilteredProducts"
_PRODUCT_URL = "https://api.gog.com/products/1234"
_DOWNLINK_URL = "https://api.gog.com/products/1234/downlink/installer/file1"


class FakeTokenStore:
    def __init__(self, access_token: str = "access", refresh_token: str = "refresh") -> None:
        self.tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": "2099-01-01T00:00:00+00:00",
            "username": "tester",
            "user_id": "123",
        }
        self.saved: list[dict] = []

    def load_tokens(self) -> dict:
        return self.tokens

    def save_tokens(self, tokens: dict) -> None:
        self.tokens = tokens
        self.saved.append(tokens)


def _make_client() -> tuple[GogApiClient, FakeTokenStore]:
    store = FakeTokenStore()
    return GogApiClient(store), store


# ── TokenStore Protocol ────────────────────────────────────────────────────────

def test_fake_token_store_satisfies_protocol() -> None:
    store: TokenStore = FakeTokenStore()
    assert store.load_tokens()["access_token"] == "access"
    store.save_tokens({"access_token": "new", "refresh_token": "r", "expires_at": "x"})
    assert store.load_tokens()["access_token"] == "new"


# ── get_owned_ids ──────────────────────────────────────────────────────────────

@rsps_lib.activate
def test_get_owned_ids_happy_path() -> None:
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, json={"owned": [1, 2, 3]})
    client, _ = _make_client()
    assert client.get_owned_ids() == [1, 2, 3]


@rsps_lib.activate
def test_get_owned_ids_401_triggers_refresh_and_retry() -> None:
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, status=401)
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={"access_token": "new_access", "refresh_token": "new_refresh", "expires_in": 3600},
    )
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, json={"owned": [10, 20]})

    client, store = _make_client()
    result = client.get_owned_ids()

    assert result == [10, 20]
    assert store.saved[0]["access_token"] == "new_access"
    assert store.saved[0]["username"] == "tester"


@rsps_lib.activate
def test_get_owned_ids_401_then_refresh_fails_raises_auth_error() -> None:
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, status=401)
    rsps_lib.add(rsps_lib.GET, _TOKEN_URL, status=400, json={"error": "invalid_grant"})

    client, _ = _make_client()
    with pytest.raises(AuthError):
        client.get_owned_ids()


@rsps_lib.activate
def test_get_owned_ids_401_after_refresh_raises_auth_error() -> None:
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, status=401)
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={"access_token": "new", "refresh_token": "r", "expires_in": 3600},
    )
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, status=401)

    client, _ = _make_client()
    with pytest.raises(AuthError):
        client.get_owned_ids()


@rsps_lib.activate
def test_get_owned_ids_network_error_raises_network_error() -> None:
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, body=ConnectionError("no route"))

    client, _ = _make_client()
    with pytest.raises(NetworkError):
        client.get_owned_ids()


@rsps_lib.activate
def test_get_owned_ids_5xx_raises_network_error() -> None:
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, status=500)

    client, _ = _make_client()
    with pytest.raises(NetworkError, match="500"):
        client.get_owned_ids()


# ── get_library_page ───────────────────────────────────────────────────────────

@rsps_lib.activate
def test_get_library_page_happy_path() -> None:
    payload = {"page": 1, "totalPages": 2, "products": [{"id": 42}]}
    rsps_lib.add(rsps_lib.GET, _LIBRARY_URL, json=payload)

    client, _ = _make_client()
    result = client.get_library_page(1)

    assert result["totalPages"] == 2
    assert result["products"][0]["id"] == 42


@rsps_lib.activate
def test_get_library_page_401_refresh_retry() -> None:
    rsps_lib.add(rsps_lib.GET, _LIBRARY_URL, status=401)
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={"access_token": "tok2", "refresh_token": "ref2", "expires_in": 3600},
    )
    rsps_lib.add(rsps_lib.GET, _LIBRARY_URL, json={"page": 1, "totalPages": 1, "products": []})

    client, store = _make_client()
    result = client.get_library_page(1)

    assert result["page"] == 1
    assert store.saved[0]["access_token"] == "tok2"


@rsps_lib.activate
def test_get_library_page_network_error() -> None:
    rsps_lib.add(rsps_lib.GET, _LIBRARY_URL, body=ConnectionError("timeout"))

    client, _ = _make_client()
    with pytest.raises(NetworkError):
        client.get_library_page(1)


@rsps_lib.activate
def test_get_library_page_4xx_raises_network_error() -> None:
    rsps_lib.add(rsps_lib.GET, _LIBRARY_URL, status=403)

    client, _ = _make_client()
    with pytest.raises(NetworkError, match="403"):
        client.get_library_page(1)


# ── get_product_downloads ──────────────────────────────────────────────────────

@rsps_lib.activate
def test_get_product_downloads_happy_path() -> None:
    payload = {"id": 1234, "downloads": {"installers": [{"id": "en1"}]}}
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL, json=payload)

    client, _ = _make_client()
    result = client.get_product_downloads(1234)

    assert result["id"] == 1234
    assert result["downloads"]["installers"][0]["id"] == "en1"


@rsps_lib.activate
def test_get_product_downloads_401_refresh_retry() -> None:
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL, status=401)
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={"access_token": "tok3", "refresh_token": "ref3", "expires_in": 3600},
    )
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL, json={"id": 1234, "downloads": {}})

    client, store = _make_client()
    result = client.get_product_downloads(1234)

    assert result["id"] == 1234
    assert store.saved[0]["access_token"] == "tok3"


@rsps_lib.activate
def test_get_product_downloads_network_error() -> None:
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL, body=ConnectionError("down"))

    client, _ = _make_client()
    with pytest.raises(NetworkError):
        client.get_product_downloads(1234)


@rsps_lib.activate
def test_get_product_downloads_refresh_failure() -> None:
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL, status=401)
    rsps_lib.add(rsps_lib.GET, _TOKEN_URL, status=401)

    client, _ = _make_client()
    with pytest.raises(AuthError):
        client.get_product_downloads(1234)


# ── resolve_downlink_url ───────────────────────────────────────────────────────

@rsps_lib.activate
def test_resolve_downlink_url_returns_tuple() -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _DOWNLINK_URL,
        json={
            "downlink": "https://cdn.gog.com/file.exe?token=xyz",
            "checksum": "https://cdn.gog.com/file.exe.xml",
        },
    )

    client, _ = _make_client()
    signed_url, checksum_url = client.resolve_downlink_url(_DOWNLINK_URL)

    assert signed_url == "https://cdn.gog.com/file.exe?token=xyz"
    assert checksum_url == "https://cdn.gog.com/file.exe.xml"


@rsps_lib.activate
def test_resolve_downlink_url_missing_checksum_returns_empty_string() -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _DOWNLINK_URL,
        json={"downlink": "https://cdn.gog.com/file.exe?token=xyz"},
    )

    client, _ = _make_client()
    signed_url, checksum_url = client.resolve_downlink_url(_DOWNLINK_URL)

    assert checksum_url == ""


@rsps_lib.activate
def test_resolve_downlink_url_401_refresh_retry() -> None:
    rsps_lib.add(rsps_lib.GET, _DOWNLINK_URL, status=401)
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={"access_token": "tok4", "refresh_token": "ref4", "expires_in": 3600},
    )
    rsps_lib.add(
        rsps_lib.GET,
        _DOWNLINK_URL,
        json={"downlink": "https://cdn.gog.com/f.exe", "checksum": ""},
    )

    client, store = _make_client()
    signed_url, _ = client.resolve_downlink_url(_DOWNLINK_URL)

    assert signed_url == "https://cdn.gog.com/f.exe"
    assert store.saved[0]["access_token"] == "tok4"


@rsps_lib.activate
def test_resolve_downlink_url_network_error() -> None:
    rsps_lib.add(rsps_lib.GET, _DOWNLINK_URL, body=ConnectionError("gone"))

    client, _ = _make_client()
    with pytest.raises(NetworkError):
        client.resolve_downlink_url(_DOWNLINK_URL)


@rsps_lib.activate
def test_resolve_downlink_url_refresh_failure() -> None:
    rsps_lib.add(rsps_lib.GET, _DOWNLINK_URL, status=401)
    rsps_lib.add(rsps_lib.GET, _TOKEN_URL, status=400)

    client, _ = _make_client()
    with pytest.raises(AuthError):
        client.resolve_downlink_url(_DOWNLINK_URL)


# ── token refresh saves tokens before returning ────────────────────────────────

@rsps_lib.activate
def test_refresh_saves_tokens_before_retry() -> None:
    """save_tokens must be called before the retried request uses the new token."""
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, status=401)
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={"access_token": "fresh", "refresh_token": "fresh_r", "expires_in": 3600},
    )
    rsps_lib.add(rsps_lib.GET, _OWNED_URL, json={"owned": []})

    client, store = _make_client()
    client.get_owned_ids()

    assert len(store.saved) == 1
    assert store.saved[0]["access_token"] == "fresh"
