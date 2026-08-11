import time

import pytest

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_password_is_not_plaintext():
    hashed = hash_password("hunter2fish")
    assert hashed != "hunter2fish"
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")


def test_verify_password_accepts_correct_and_rejects_wrong():
    hashed = hash_password("correct-horse-1")
    assert verify_password("correct-horse-1", hashed) is True
    assert verify_password("wrong-horse-1", hashed) is False


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert "exp" in payload and "iat" in payload


def test_decode_rejects_garbage_token():
    assert decode_access_token("not-a-real-jwt") is None


def test_decode_rejects_expired_token():
    from datetime import timedelta

    token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None


def test_decode_rejects_token_signed_with_different_secret():
    from jose import jwt

    bad_token = jwt.encode({"sub": "user-123"}, "a-completely-different-secret", algorithm="HS256")
    assert decode_access_token(bad_token) is None
