# tests/test_behavior_projects_auth.py
import os
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.projects import router as projects_router
from database import get_db

# Make sure JWT_SECRET exists so auth import doesn't crash
os.environ.setdefault("JWT_SECRET", "test-secret")


def fake_get_db():
    # dependency override: we never hit the DB because auth fails first
    yield None


def test_get_projects_requires_auth():
    app = FastAPI()
    app.include_router(projects_router, prefix="/api/projects")

    # override DB dependency so we don't need Postgres running
    app.dependency_overrides[get_db] = fake_get_db

    client = TestClient(app)
    resp = client.get("/api/projects/")
    assert resp.status_code in (401, 403)