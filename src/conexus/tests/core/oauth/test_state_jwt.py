import time
import secrets
import pytest
from conexus.core.oauth.state import encode_state, decode_state, StateExpired, StateInvalid

SECRET = b"x" * 32


def test_round_trip():
    nonce = secrets.token_urlsafe(16)
    tok = encode_state(SECRET, user_id="u1", server_url="https://mcp.example/",
                       return_to="tg://chat/123", nonce=nonce)
    payload = decode_state(SECRET, tok)
    assert payload.user_id == "u1"
    assert payload.server_url == "https://mcp.example/"
    assert payload.return_to == "tg://chat/123"
    assert payload.nonce == nonce
    # verifier NOT in payload — stored server-side


def test_expired(monkeypatch):
    nonce = secrets.token_urlsafe(16)
    tok = encode_state(SECRET, user_id="u1", server_url="x", return_to="y",
                       nonce=nonce, ttl_seconds=1)
    monkeypatch.setattr("conexus.core.oauth.state._now", lambda: time.time() + 10)
    with pytest.raises(StateExpired):
        decode_state(SECRET, tok)


def test_tampered():
    nonce = secrets.token_urlsafe(16)
    tok = encode_state(SECRET, user_id="u1", server_url="x", return_to="y", nonce=nonce)
    with pytest.raises(StateInvalid):
        decode_state(b"y" * 32, tok)


def test_secret_too_short():
    with pytest.raises(ValueError):
        encode_state(b"short", user_id="u1", server_url="x", return_to="y",
                     nonce=secrets.token_urlsafe(16))
