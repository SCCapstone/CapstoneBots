"""
Account Deletion Tests

Tests for the DELETE /api/auth/account endpoint to verify:
1. Successful account deletion with correct password
2. Wrong password is rejected
3. Deleted user cannot log in
4. Unauthenticated request is rejected
"""

import pytest

from conftest import requires_db, register_and_login, auth_header


pytestmark = requires_db


def test_delete_account_success(client):
    """Deleting account with correct password succeeds and user is removed."""
    user, token, email, _ = register_and_login(client)

    # Delete account
    r = client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "testpass123"},
        headers=auth_header(token),
    )
    assert r.status_code == 204, r.text

    # Confirm user cannot log in anymore
    r = client.post("/api/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    assert r.status_code == 401


def test_delete_account_wrong_password(client):
    """Deleting account with wrong password is rejected."""
    _, token, _, _ = register_and_login(client)

    r = client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "wrong_password"},
        headers=auth_header(token),
    )
    assert r.status_code == 401
    assert "Incorrect password" in r.json()["detail"]


def test_delete_account_no_auth(client):
    """Deleting account without authentication is rejected."""
    r = client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "anything"},
    )
    # Should be 401 or 403 (no Bearer token)
    assert r.status_code in (401, 403)


def test_deleted_user_cannot_access_me(client):
    """After deletion, the old token should not work for /me."""
    _, token, _, _ = register_and_login(client)

    # Delete account
    r = client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "testpass123"},
        headers=auth_header(token),
    )
    assert r.status_code == 204

    # Try to access /me with the old token
    r = client.get(
        "/api/auth/me",
        headers=auth_header(token),
    )
    assert r.status_code == 401
