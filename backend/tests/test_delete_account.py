"""
Account Deletion Tests

Tests for the DELETE /api/auth/account endpoint to verify:
1. Successful account deletion with correct password
2. Wrong password is rejected
3. Deleted user cannot log in
4. Unauthenticated request is rejected
"""

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


def _register_and_login(client, username=None, email=None, password="testpass123"):
    """Helper: register a user and return (user_data, access_token)."""
    username = username or f"user_{uuid4().hex[:8]}"
    email = email or f"{uuid4().hex[:8]}@example.com"

    r = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
    })
    assert r.status_code == 201, r.text
    user_data = r.json()

    r = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    return user_data, token


def test_delete_account_success():
    """Deleting account with correct password succeeds and user is removed."""
    with TestClient(app) as client:
        user, token = _register_and_login(client)
        email = user["email"]

        # Delete account
        r = client.request(
            "DELETE",
            "/api/auth/account",
            json={"password": "testpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204, r.text

        # Confirm user cannot log in anymore
        r = client.post("/api/auth/login", json={
            "email": email,
            "password": "testpass123",
        })
        assert r.status_code == 401


def test_delete_account_wrong_password():
    """Deleting account with wrong password is rejected."""
    with TestClient(app) as client:
        _, token = _register_and_login(client)

        r = client.request(
            "DELETE",
            "/api/auth/account",
            json={"password": "wrong_password"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
        assert "Incorrect password" in r.json()["detail"]


def test_delete_account_no_auth():
    """Deleting account without authentication is rejected."""
    with TestClient(app) as client:
        r = client.request(
            "DELETE",
            "/api/auth/account",
            json={"password": "anything"},
        )
        # Should be 401 or 403 (no Bearer token)
        assert r.status_code in (401, 403)


def test_deleted_user_cannot_access_me():
    """After deletion, the old token should not work for /me."""
    with TestClient(app) as client:
        _, token = _register_and_login(client)

        # Delete account
        r = client.request(
            "DELETE",
            "/api/auth/account",
            json={"password": "testpass123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204

        # Try to access /me with the old token
        r = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
