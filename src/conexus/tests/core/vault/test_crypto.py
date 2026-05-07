from conexus.core.vault.crypto import decrypt, derive_key, encrypt

KEY = derive_key(b"master-secret-32-bytes-padding!!", salt=b"user_id_salt")


def test_round_trip():
    ct = encrypt(KEY, b"refresh_token_value")
    assert ct != b"refresh_token_value"
    assert decrypt(KEY, ct) == b"refresh_token_value"


def test_tamper_detected():
    import pytest

    ct = bytearray(encrypt(KEY, b"data"))
    ct[-1] ^= 0xFF
    with pytest.raises(Exception):
        decrypt(KEY, bytes(ct))
