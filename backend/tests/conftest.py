"""
Pytest configuration for the backend test suite.

Adds the backend root directory to sys.path so test modules can import
application modules (schemas, models, utils, storage, etc.) directly.
Provides shared fixtures and helpers for all integration tests.
"""

import sys
import os
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

# Add the backend root (parent of tests/) to sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

# Set JWT_SECRET for tests that import auth utilities
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")

# Support TEST_DATABASE_URL: override DATABASE_URL before any app import
_test_db_url = os.environ.get("TEST_DATABASE_URL")
if _test_db_url:
    os.environ["DATABASE_URL"] = _test_db_url

from main import app  # noqa: E402
from utils.auth import create_email_verification_token  # noqa: E402


# --------------- DB availability check ---------------

def _db_available():
    """Check if the test database is reachable."""
    try:
        with TestClient(app) as c:
            r = c.get("/api/health")
            return r.status_code == 200
    except Exception:
        return False


_DB_UP = _db_available()

requires_db = pytest.mark.skipif(
    not _DB_UP,
    reason="PostgreSQL database not available (start with: docker compose up -d db && alembic upgrade head)",
)


# --------------- Shared helpers ---------------

def verify_email(client, email: str):
    """Generate a verification token and call /api/auth/verify-email."""
    token = create_email_verification_token(email)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    return r


def register(client, prefix="test", username=None, email=None, password="testpass123"):
    """Register a new user with a random username/email."""
    username = username or f"{prefix}_{uuid4().hex[:8]}"
    email = email or f"{prefix}_{uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 201, r.text
    return r.json(), email, password


def register_and_login(client, prefix="test", username=None, email=None, password="testpass123"):
    """Register a user, verify email, login, and return (user_data, token, email, username)."""
    user_data, email, password = register(client, prefix, username, email, password)
    verify_email(client, email)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return user_data, token, email, user_data["username"]


def auth_header(token):
    """Build Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


def create_project(client, token, name=None):
    """Create a project and return the response JSON."""
    name = name or f"Project {uuid4().hex[:6]}"
    r = client.post(
        "/api/projects",
        json={"name": name, "description": "test"},
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


def get_main_branch(client, token, project_id):
    """Fetch the 'main' branch for a project."""
    r = client.get(f"/api/projects/{project_id}/branches", headers=auth_header(token))
    assert r.status_code == 200, r.text
    main = [b for b in r.json() if b["branch_name"] == "main"]
    assert main, "main branch not found"
    return main[0]


def make_commit(client, token, project_id, branch_id, message="test commit", objects=None):
    """Create a commit and return the raw response."""
    objects = objects or [{
        "object_name": f"Obj_{uuid4().hex[:6]}",
        "object_type": "MESH",
        "json_data_path": f"test/{uuid4().hex[:6]}.json",
        "blob_hash": uuid4().hex[:12],
    }]
    r = client.post(
        f"/api/projects/{project_id}/commits",
        json={"branch_id": branch_id, "commit_message": message, "objects": objects},
        headers=auth_header(token),
    )
    return r


def invite_and_accept(client, project_id, owner_token, invitee_email, invitee_token, role="editor"):
    """Owner invites a user and the invitee accepts."""
    r = client.post(
        f"/api/projects/{project_id}/invitations",
        json={"email": invitee_email, "role": role},
        headers=auth_header(owner_token),
    )
    assert r.status_code == 201, f"Invite failed: {r.text}"
    invitation_id = r.json()["invitation_id"]
    r = client.post(
        f"/api/auth/invitations/{invitation_id}/accept",
        headers=auth_header(invitee_token),
    )
    assert r.status_code in (200, 201), f"Accept failed: {r.text}"
    return invitation_id


def naive_future(hours=1):
    """Return an ISO string for a naive-UTC timestamp in the future."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(tzinfo=None).isoformat()


# --------------- Shared fixtures ---------------

@pytest.fixture()
def client():
    """Provide a sync TestClient wrapping the FastAPI app."""
    with TestClient(app) as c:
        yield c
