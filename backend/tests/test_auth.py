import sys
import os
from fastapi.testclient import TestClient
from uuid import uuid4

# Ensure the application root is on sys.path when pytest runs from inside /app/tests
root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)

import importlib.util

# Load main.py directly to avoid pytest import path issues
spec = importlib.util.spec_from_file_location("main", os.path.join(root, "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
app = main.app

from utils import auth
from utils.auth import create_email_verification_token


def _verify_email(client, email: str):
    """Helper: generate a verification token and call /api/auth/verify-email."""
    token = create_email_verification_token(email)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    return r


def test_register_and_login():
    # Ensure we can register a new user, verify email, and then login
    username = f"testuser_{uuid4().hex[:8]}"
    email = f"test_{uuid4().hex[:8]}@example.com"
    password = "s3cret123"

    with TestClient(app) as client:
        # Register
        r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == email
        assert "user_id" in body

        # Verify email before logging in
        _verify_email(client, email)

        # Login
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        token_resp = r.json()
        assert "access_token" in token_resp
        assert token_resp["token_type"] == "bearer"

        # Verify token decodes and contains sub
        payload = auth.decode_access_token(token_resp["access_token"])
        assert payload.get("sub") == email


def test_login_blocked_before_verification():
    """Login should be rejected with 403 when email is not yet verified."""
    username = f"unverified_{uuid4().hex[:8]}"
    email = f"unverified_{uuid4().hex[:8]}@example.com"
    password = "s3cret123"

    with TestClient(app) as client:
        # Register (email is unverified)
        r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
        assert r.status_code == 201, r.text

        # Attempt login without verifying email
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "EMAIL_NOT_VERIFIED"
        assert "not verified" in detail["message"].lower()


def test_verify_email_flow():
    """Verify-email endpoint marks the account as verified and allows login."""
    username = f"verifyflow_{uuid4().hex[:8]}"
    email = f"verifyflow_{uuid4().hex[:8]}@example.com"
    password = "s3cret123"

    with TestClient(app) as client:
        # Register
        r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
        assert r.status_code == 201, r.text

        # Verify email
        _verify_email(client, email)

        # Calling verify again should indicate already verified
        token = create_email_verification_token(email)
        r = client.post("/api/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text
        assert "already verified" in r.json()["message"].lower()

        # Login should now succeed
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()


def test_verify_email_invalid_token():
    """An invalid/expired verification token should be rejected."""
    with TestClient(app) as client:
        r = client.post("/api/auth/verify-email", json={"token": "garbage.token.value"})
        assert r.status_code == 400, r.text


def test_me_endpoint():
    # Test the /me endpoint returns authenticated user's information
    username = f"meuser_{uuid4().hex[:8]}"
    email = f"me_{uuid4().hex[:8]}@example.com"
    password = "mypassword"

    with TestClient(app) as client:
        # Register a new user
        r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
        assert r.status_code == 201, r.text
        registered_user = r.json()

        # Verify email before logging in
        _verify_email(client, email)

        # Login to get the access token
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        token_resp = r.json()
        access_token = token_resp["access_token"]

        # Call /me endpoint with the token
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert r.status_code == 200, r.text
        me_data = r.json()

        # Verify the returned user information matches the registered user
        assert me_data["user_id"] == registered_user["user_id"]
        assert me_data["username"] == username
        assert me_data["email"] == email
