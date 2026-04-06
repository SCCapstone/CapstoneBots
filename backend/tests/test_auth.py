import pytest
from uuid import uuid4

from conftest import requires_db, verify_email
from utils import auth
from utils.auth import create_email_verification_token


pytestmark = requires_db


def test_register_and_login(client):
    # Ensure we can register a new user, verify email, and then login
    username = f"testuser_{uuid4().hex[:8]}"
    email = f"test_{uuid4().hex[:8]}@example.com"
    password = "s3cret123"

    # Register
    r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email
    assert "user_id" in body

    # Verify email before logging in
    verify_email(client, email)

    # Login
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token_resp = r.json()
    assert "access_token" in token_resp
    assert token_resp["token_type"] == "bearer"

    # Verify token decodes and contains sub
    payload = auth.decode_access_token(token_resp["access_token"])
    assert payload.get("sub") == email


def test_login_blocked_before_verification(client):
    """Login should be rejected with 403 when email is not yet verified."""
    username = f"unverified_{uuid4().hex[:8]}"
    email = f"unverified_{uuid4().hex[:8]}@example.com"
    password = "s3cret123"

    # Register (email is unverified)
    r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    assert r.status_code == 201, r.text

    # Attempt login without verifying email
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "EMAIL_NOT_VERIFIED"
    assert "not verified" in detail["message"].lower()


def test_verify_email_flow(client):
    """Verify-email endpoint marks the account as verified and allows login."""
    username = f"verifyflow_{uuid4().hex[:8]}"
    email = f"verifyflow_{uuid4().hex[:8]}@example.com"
    password = "s3cret123"

    # Register
    r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    assert r.status_code == 201, r.text

    # Verify email
    verify_email(client, email)

    # Calling verify again should indicate already verified
    token = create_email_verification_token(email)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert "already verified" in r.json()["message"].lower()

    # Login should now succeed
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


def test_verify_email_invalid_token(client):
    """An invalid/expired verification token should be rejected."""
    r = client.post("/api/auth/verify-email", json={"token": "garbage.token.value"})
    assert r.status_code == 400, r.text


def test_me_endpoint(client):
    # Test the /me endpoint returns authenticated user's information
    username = f"meuser_{uuid4().hex[:8]}"
    email = f"me_{uuid4().hex[:8]}@example.com"
    password = "mypassword"

    # Register a new user
    r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    assert r.status_code == 201, r.text
    registered_user = r.json()

    # Verify email before logging in
    verify_email(client, email)

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


def test_refresh_token(client):
    """A valid token can be refreshed for a new one."""
    username = f"refresh_{uuid4().hex[:8]}"
    email = f"refresh_{uuid4().hex[:8]}@example.com"
    password = "refreshpass"

    client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    verify_email(client, email)

    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    original_token = r.json()["access_token"]

    # Refresh
    r = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {original_token}"})
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"

    # New token should work
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_refresh_token_without_auth(client):
    """Refresh without a token should fail."""
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401
