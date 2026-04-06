# tests/test_behavior_projects_auth.py
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.projects import router as projects_router
from database import get_db


def fake_get_db():
    # dependency override: we never hit the DB because auth fails first
    yield None


def test_get_projects_requires_auth():
    app = FastAPI()
    app.include_router(projects_router, prefix="/api/projects")

    # override DB dependency so we don't need Postgres running
    app.dependency_overrides[get_db] = fake_get_db

    with TestClient(app) as client:
        resp = client.get("/api/projects/")
        assert resp.status_code in (401, 403)