"""
Unit Tests for Authentication Utilities (backend/utils/auth.py)

Tests password hashing, JWT token creation/decoding, and token purpose claims.
These tests run without a database — they exercise pure utility functions.
"""

import os
import pytest
from datetime import timedelta, datetime, timezone
from jose import jwt, JWTError

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")

from utils.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    create_password_reset_token,
    decode_password_reset_token,
    create_email_verification_token,
    decode_email_verification_token,
    _prehash,
    SECRET_KEY,
    ALGORITHM,
)


# ============== Password Hashing ==============

class TestPasswordHashing:
    """Tests for bcrypt password hashing with SHA-256 pre-hashing."""

    def test_hash_and_verify_basic(self):
        """Hashing and verifying a normal password works."""
        pw = "securePassword1"
        hashed = get_password_hash(pw)
        assert verify_password(pw, hashed) is True

    def test_verify_wrong_password_fails(self):
        """Wrong password does not verify."""
        hashed = get_password_hash("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_is_unique_per_call(self):
        """Two hashes of the same password differ (random salt)."""
        pw = "samepassword"
        h1 = get_password_hash(pw)
        h2 = get_password_hash(pw)
        assert h1 != h2  # different salts

    def test_long_password_handled(self):
        """Passwords longer than bcrypt's 72-byte limit still hash/verify via pre-hash."""
        long_pw = "a" * 200
        hashed = get_password_hash(long_pw)
        assert verify_password(long_pw, hashed) is True

    def test_password_too_short_raises(self):
        """Password shorter than 8 chars raises ValueError."""
        with pytest.raises(ValueError, match="at least 8 characters"):
            get_password_hash("short")

    def test_empty_password_raises(self):
        """Empty password raises ValueError."""
        with pytest.raises(ValueError, match="at least 8 characters"):
            get_password_hash("")

    def test_verify_password_with_invalid_hash_returns_false(self):
        """Gracefully returns False for a malformed hash string."""
        assert verify_password("anything", "not-a-real-hash") is False

    def test_unicode_password(self):
        """Unicode passwords hash and verify correctly."""
        pw = "contraseña🔒segura"
        hashed = get_password_hash(pw)
        assert verify_password(pw, hashed) is True

    def test_prehash_returns_bytes(self):
        """_prehash always returns bytes."""
        result = _prehash("hello")
        assert isinstance(result, bytes)


# ============== Access Token ==============

class TestAccessToken:
    """Tests for JWT access token creation and decoding."""

    def test_create_and_decode(self):
        """Create a token and decode it to retrieve the subject."""
        token = create_access_token({"sub": "user@example.com"})
        payload = decode_access_token(token)
        assert payload["sub"] == "user@example.com"

    def test_token_contains_standard_claims(self):
        """Token includes exp, iat, nbf claims."""
        token = create_access_token({"sub": "user@example.com"})
        payload = decode_access_token(token)
        assert "exp" in payload
        assert "iat" in payload
        assert "nbf" in payload

    def test_custom_expiry(self):
        """Custom expiry delta is respected."""
        token = create_access_token(
            {"sub": "user@example.com"},
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        diff = (exp - iat).total_seconds()
        assert 290 <= diff <= 310  # ~5 min

    def test_missing_sub_raises(self):
        """Creating a token without 'sub' raises ValueError."""
        with pytest.raises(ValueError, match="sub"):
            create_access_token({"email": "no-sub@example.com"})

    def test_none_data_raises(self):
        """None data raises ValueError."""
        with pytest.raises(ValueError):
            create_access_token(None)

    def test_empty_dict_raises(self):
        """Empty dict raises ValueError."""
        with pytest.raises(ValueError):
            create_access_token({})

    def test_decode_garbage_token_raises(self):
        """Garbage string raises JWTError."""
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.jwt")

    def test_decode_expired_token_raises(self):
        """An already-expired token raises JWTError."""
        token = create_access_token(
            {"sub": "user@example.com"},
            expires_delta=timedelta(seconds=-10),
        )
        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_decode_tampered_token_raises(self):
        """Altering the payload after signing raises JWTError."""
        token = create_access_token({"sub": "user@example.com"})
        # flip the last char
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(JWTError):
            decode_access_token(tampered)

    def test_extra_claims_preserved(self):
        """Extra claims passed in data are preserved in the decoded token."""
        token = create_access_token({"sub": "u@e.com", "role": "admin"})
        payload = decode_access_token(token)
        assert payload["role"] == "admin"


# ============== Password Reset Token ==============

class TestPasswordResetToken:
    """Tests for the password-reset purpose token."""

    def test_create_and_decode(self):
        """Round-trip create → decode works."""
        token = create_password_reset_token("user@example.com")
        payload = decode_password_reset_token(token)
        assert payload["sub"] == "user@example.com"
        assert payload["purpose"] == "password-reset"

    def test_wrong_purpose_rejected(self):
        """An access token (no purpose claim) is rejected as reset token."""
        access_tok = create_access_token({"sub": "user@example.com"})
        with pytest.raises(ValueError, match="not a valid password-reset"):
            decode_password_reset_token(access_tok)

    def test_email_verification_token_rejected_as_reset(self):
        """An email-verification token is rejected when decoded as reset."""
        verify_tok = create_email_verification_token("user@example.com")
        with pytest.raises(ValueError, match="not a valid password-reset"):
            decode_password_reset_token(verify_tok)

    def test_garbage_token_raises(self):
        """Invalid token string raises JWTError."""
        with pytest.raises(JWTError):
            decode_password_reset_token("garbage")


# ============== Email Verification Token ==============

class TestEmailVerificationToken:
    """Tests for the email-verification purpose token."""

    def test_create_and_decode(self):
        """Round-trip create → decode works."""
        token = create_email_verification_token("user@example.com")
        payload = decode_email_verification_token(token)
        assert payload["sub"] == "user@example.com"
        assert payload["purpose"] == "email-verification"

    def test_wrong_purpose_rejected(self):
        """A password-reset token is rejected when decoded as verification."""
        reset_tok = create_password_reset_token("user@example.com")
        with pytest.raises(ValueError, match="not a valid email-verification"):
            decode_email_verification_token(reset_tok)

    def test_access_token_rejected(self):
        """An access token is rejected when decoded as verification."""
        access_tok = create_access_token({"sub": "user@example.com"})
        with pytest.raises(ValueError, match="not a valid email-verification"):
            decode_email_verification_token(access_tok)

    def test_garbage_token_raises(self):
        """Invalid token string raises JWTError."""
        with pytest.raises(JWTError):
            decode_email_verification_token("garbage.token.value")
