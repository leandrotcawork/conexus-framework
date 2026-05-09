"""Tests for GitHub App JWT signing and token minting."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _generate_pem() -> tuple[str, object]:
    """Return (pem_str, public_key) for a fresh RSA key."""
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


def test_make_jwt_encodes_app_id():
    from conexus.core.memory.wiki.git_auth import _make_jwt

    pem, pub = _generate_pem()
    token = _make_jwt("123", pem)
    payload = jwt.decode(token, pub, algorithms=["RS256"])
    assert payload["iss"] == "123"


def test_make_jwt_expiry_window():
    import time
    from conexus.core.memory.wiki.git_auth import _make_jwt

    pem, pub = _generate_pem()
    before = int(time.time())
    token = _make_jwt("app1", pem)
    payload = jwt.decode(token, pub, algorithms=["RS256"])
    assert payload["iat"] <= before
    assert payload["exp"] > before
    assert payload["exp"] - payload["iat"] <= 600  # <=10 min per GitHub limit


def test_get_installation_token_calls_github():
    from conexus.core.memory.wiki.git_auth import _TOKEN_CACHE, get_installation_token

    _TOKEN_CACHE.clear()
    pem, _ = _generate_pem()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"token": "ghs_abc", "expires_at": "2099-01-01T00:00:00Z"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        token = get_installation_token("app123", pem, 42)

    assert token == "ghs_abc"
    mock_post.assert_called_once()
    assert "42" in mock_post.call_args[0][0]


def test_token_cached_on_second_call():
    from conexus.core.memory.wiki.git_auth import _TOKEN_CACHE, get_installation_token

    _TOKEN_CACHE.clear()
    pem, _ = _generate_pem()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"token": "ghs_xyz", "expires_at": "2099-01-01T00:00:00Z"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        get_installation_token("app", pem, 99)
        get_installation_token("app", pem, 99)

    assert mock_post.call_count == 1  # second call uses cache
