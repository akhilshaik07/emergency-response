"""Unit tests for app.core.security auth utilities."""

import pytest
from datetime import timedelta
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenExpiredError,
    TokenInvalidError,
)


def test_password_hashing_and_verification():
    raw_password = "SuperSecurePassword123!"
    hashed = hash_password(raw_password)
    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True


def test_wrong_password_fails():
    raw_password = "CorrectPassword123!"
    wrong_password = "WrongPassword456!"
    hashed = hash_password(raw_password)
    assert verify_password(wrong_password, hashed) is False


def test_access_token_creation_and_decoding():
    user_id = "11111111-2222-3333-4444-555555555555"
    role = "resident"
    token = create_access_token(subject=user_id, role=role)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == role
    assert payload["type"] == "access"
    assert "exp" in payload


def test_refresh_token_creation_and_decoding():
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_refresh_token(subject=user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"
    assert "role" not in payload  # Refresh tokens carry minimal data
    assert "exp" in payload


def test_expired_token_raises_token_expired_error():
    user_id = "11111111-2222-3333-4444-555555555555"
    # Create token expired 10 minutes ago
    expired_token = create_access_token(
        subject=user_id,
        role="volunteer",
        expires_delta=timedelta(minutes=-10),
    )
    with pytest.raises(TokenExpiredError, match="Token has expired"):
        decode_token(expired_token)


def test_tampered_token_raises_token_invalid_error():
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_access_token(subject=user_id, role="admin")
    # Tamper with the last character of the JWT signature
    tampered_char = "X" if token[-1] != "X" else "Y"
    tampered_token = token[:-1] + tampered_char
    with pytest.raises(TokenInvalidError, match="Token signature or structure is invalid"):
        decode_token(tampered_token)
