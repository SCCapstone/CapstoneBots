import sys
import os
from fastapi.testclient import TestClient

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


def test_register_and_login():
    # Ensure we can register a new user and then login to receive a token
    username = "testuser"
    email = "test@example.com"
    password = "s3cret"

    with TestClient(app) as client:
        # Register
        r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == email
        assert "user_id" in body

        # Login
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        token_resp = r.json()
        assert "access_token" in token_resp
        assert token_resp["token_type"] == "bearer"

        # Verify token decodes and contains sub
        payload = auth.decode_access_token(token_resp["access_token"])
        assert payload.get("sub") == email


def test_me_endpoint():
    # Test the /me endpoint returns authenticated user's information
    username = "meuser"
    email = "me@example.com"
    password = "mypassword"

    with TestClient(app) as client:
        # Register a new user
        r = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
        assert r.status_code == 201, r.text
        registered_user = r.json()

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
