from conexus.core.oauth.pkce import generate_pkce_pair, verify_challenge


def test_pair_lengths_and_charset():
    verifier, challenge, method = generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert all(c.isalnum() or c in "-._~" for c in verifier)
    assert method == "S256"
    assert len(challenge) == 43  # base64url(sha256) no padding


def test_round_trip():
    verifier, challenge, _ = generate_pkce_pair()
    assert verify_challenge(verifier, challenge)
