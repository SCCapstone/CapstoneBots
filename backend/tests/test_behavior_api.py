"""
Behavioral Tests for API Endpoints

Tests the API from a user's perspective: register, login, create projects,
verify email, access protected routes, and error handling.
These tests require a running PostgreSQL database.
Run with: docker compose up -d db && cd backend && pytest tests/test_behavior_api.py -v
"""

import pytest
from uuid import uuid4

from conftest import (
    requires_db, verify_email, register, register_and_login, auth_header,
)
from utils.auth import create_email_verification_token


pytestmark = requires_db


# ============== Health Check ==============

class TestHealthCheck:
    def test_health_returns_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ============== Registration Behavior ==============

class TestRegistration:
    def test_register_returns_user_id_and_email(self, client):
        user, email, _ = register(client)
        assert "user_id" in user
        assert user["email"] == email

    def test_duplicate_email_rejected(self, client):
        email = f"dup_{uuid4().hex[:8]}@example.com"
        register(client, email=email)
        r = client.post("/api/auth/register", json={
            "username": f"user2_{uuid4().hex[:8]}",
            "email": email,
            "password": "testpass123",
        })
        assert r.status_code in (400, 409)

    def test_duplicate_username_rejected(self, client):
        username = f"dupuser_{uuid4().hex[:8]}"
        register(client, username=username)
        r = client.post("/api/auth/register", json={
            "username": username,
            "email": f"other_{uuid4().hex[:8]}@example.com",
            "password": "testpass123",
        })
        assert r.status_code in (400, 409)


# ============== Login Behavior ==============

class TestLoginBehavior:
    def test_successful_login(self, client):
        _, token, _, _ = register_and_login(client)
        assert token is not None
        assert len(token) > 20

    def test_wrong_password_rejected(self, client):
        _, email, _ = register(client)
        verify_email(client, email)
        r = client.post("/api/auth/login", json={
            "email": email,
            "password": "wrong_password",
        })
        assert r.status_code == 401

    def test_nonexistent_user_rejected(self, client):
        r = client.post("/api/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "doesntmatter",
        })
        assert r.status_code == 401

    def test_login_blocked_before_verification(self, client):
        _, email, password = register(client)
        r = client.post("/api/auth/login", json={
            "email": email,
            "password": password,
        })
        assert r.status_code == 403


# ============== Protected Routes ==============

class TestProtectedRoutes:
    def test_projects_require_auth(self, client):
        r = client.get("/api/projects/")
        assert r.status_code in (401, 403)

    def test_me_requires_auth(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code in (401, 403)

    def test_me_with_valid_token(self, client):
        user, token, email, _ = register_and_login(client)
        r = client.get("/api/auth/me", headers=auth_header(token))
        assert r.status_code == 200
        me = r.json()
        assert me["email"] == email
        assert me["user_id"] == user["user_id"]

    def test_me_with_invalid_token(self, client):
        r = client.get("/api/auth/me", headers=auth_header("bad.token.here"))
        assert r.status_code == 401


# ============== Project CRUD Behavior ==============

class TestProjectCRUD:
    def test_create_project(self, client):
        _, token, _, _ = register_and_login(client)
        r = client.post(
            "/api/projects/",
            json={"name": "Test Project", "description": "A test"},
            headers=auth_header(token),
        )
        assert r.status_code == 201
        proj = r.json()
        assert proj["name"] == "Test Project"
        assert "project_id" in proj
        assert proj["default_branch"] == "main"

    def test_list_projects(self, client):
        _, token, _, _ = register_and_login(client)
        # create 2 projects
        client.post("/api/projects/", json={"name": "P1"}, headers=auth_header(token))
        client.post("/api/projects/", json={"name": "P2"}, headers=auth_header(token))
        r = client.get("/api/projects/", headers=auth_header(token))
        assert r.status_code == 200
        projects = r.json()
        assert len(projects) >= 2

    def test_create_project_empty_name_rejected(self, client):
        _, token, _, _ = register_and_login(client)
        r = client.post(
            "/api/projects/",
            json={"name": ""},
            headers=auth_header(token),
        )
        # Should be rejected (400 or 422) depending on backend validation
        assert r.status_code in (400, 422)

    def test_get_nonexistent_project(self, client):
        _, token, _, _ = register_and_login(client)
        fake_id = str(uuid4())
        r = client.get(f"/api/projects/{fake_id}", headers=auth_header(token))
        assert r.status_code in (403, 404)

    def test_delete_project(self, client):
        _, token, _, _ = register_and_login(client)
        r = client.post(
            "/api/projects/",
            json={"name": "ToDelete"},
            headers=auth_header(token),
        )
        proj_id = r.json()["project_id"]
        r = client.delete(f"/api/projects/{proj_id}", headers=auth_header(token))
        assert r.status_code in (200, 204)


# ============== Email Verification Behavior ==============

class TestEmailVerification:
    def test_verify_email_enables_login(self, client):
        _, email, password = register(client)
        # login blocked
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 403
        # verify
        verify_email(client, email)
        # login now works
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200

    def test_double_verification_says_already_verified(self, client):
        _, email, _ = register(client)
        verify_email(client, email)
        token = create_email_verification_token(email)
        r = client.post("/api/auth/verify-email", json={"token": token})
        assert r.status_code == 200
        assert "already verified" in r.json()["message"].lower()

    def test_verify_invalid_token_rejected(self, client):
        r = client.post("/api/auth/verify-email", json={"token": "bad.token"})
        assert r.status_code == 400


# ============== Account Deletion Behavior ==============

class TestAccountDeletion:
    def test_delete_account_then_login_fails(self, client):
        _, token, email, _ = register_and_login(client)
        r = client.request(
            "DELETE", "/api/auth/account",
            json={"password": "testpass123"},
            headers=auth_header(token),
        )
        assert r.status_code == 204
        r = client.post("/api/auth/login", json={"email": email, "password": "testpass123"})
        assert r.status_code == 401

    def test_delete_account_wrong_password(self, client):
        _, token, _, _ = register_and_login(client)
        r = client.request(
            "DELETE", "/api/auth/account",
            json={"password": "wrong"},
            headers=auth_header(token),
        )
        assert r.status_code == 401

    def test_delete_account_no_auth(self, client):
        r = client.request(
            "DELETE", "/api/auth/account",
            json={"password": "anything"},
        )
        assert r.status_code in (401, 403)
