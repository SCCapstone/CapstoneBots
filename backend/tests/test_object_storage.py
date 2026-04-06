"""
Tests for the object-level VCS storage endpoints.

Tests the stage-upload and download-url endpoints added for
the object-level version control flow.
"""
import sys
import os
import json
import io
from uuid import uuid4
from unittest.mock import patch, MagicMock

import pytest

# Ensure the application root is on sys.path
root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)

import importlib.util

spec = importlib.util.spec_from_file_location("main", os.path.join(root, "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
app = main.app

from fastapi.testclient import TestClient
from utils import auth
from utils.auth import create_email_verification_token


# ── Helpers ──────────────────────────────────────────────────────────────────

def _register_and_login(client) -> tuple[str, str]:
    """Register a user, verify email, login, return (token, user_id)."""
    username = f"testuser_{uuid4().hex[:8]}"
    email = f"test_{uuid4().hex[:8]}@example.com"
    password = "testpass123"

    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password
    })
    assert r.status_code == 201, r.text
    user_id = r.json()["user_id"]

    token = create_email_verification_token(email)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text

    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


def _create_project(client, token: str) -> str:
    """Create a project, return project_id."""
    r = client.post(
        "/api/projects",
        json={"name": f"TestProject_{uuid4().hex[:6]}", "description": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _get_main_branch_id(client, token: str, project_id: str) -> str:
    """Get the main branch ID for a project."""
    r = client.get(
        f"/api/projects/{project_id}/branches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    branches = r.json()
    main = next(b for b in branches if b["branch_name"] == "main")
    return main["branch_id"]


# ── Tests ────────────────────────────────────────────────────────────────────

class TestStageUpload:

    def test_stage_upload_json_only(self):
        """Upload JSON metadata without mesh data."""
        with TestClient(app) as client:
            token, user_id = _register_and_login(client)
            project_id = _create_project(client, token)

            metadata = {"object_name": "Cube", "object_type": "CAMERA", "transform": {}}
            blob_hash = "a" * 64

            r = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={
                    "object_name": "Camera",
                    "object_type": "CAMERA",
                    "blob_hash": blob_hash,
                },
                files={
                    "json_file": ("metadata.json", io.BytesIO(json.dumps(metadata).encode()), "application/json"),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 201, r.text
            data = r.json()
            assert data["object_name"] == "Camera"
            assert data["object_type"] == "CAMERA"
            assert data["json_path"].startswith(f"projects/{project_id}/")
            assert data["mesh_path"] is None
            assert data["blob_hash"] == blob_hash
            assert data["json_size"] > 0

    def test_stage_upload_with_mesh(self):
        """Upload JSON metadata + binary mesh data."""
        with TestClient(app) as client:
            token, user_id = _register_and_login(client)
            project_id = _create_project(client, token)

            metadata = {"object_name": "Cube", "vertices": [[0, 0, 0]]}
            mesh_binary = b"\x00\x01\x02\x03mesh-data-here"
            blob_hash = "b" * 64

            r = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={
                    "object_name": "Cube",
                    "object_type": "MESH",
                    "blob_hash": blob_hash,
                },
                files={
                    "json_file": ("metadata.json", io.BytesIO(json.dumps(metadata).encode()), "application/json"),
                    "mesh_file": ("mesh.bin", io.BytesIO(mesh_binary), "application/octet-stream"),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 201, r.text
            data = r.json()
            assert data["json_path"] is not None
            assert data["mesh_path"] is not None
            assert data["mesh_path"].endswith(".bin")
            assert data["mesh_size"] == len(mesh_binary)

    def test_stage_upload_invalid_blob_hash(self):
        """Reject upload with invalid blob_hash."""
        with TestClient(app) as client:
            token, _ = _register_and_login(client)
            project_id = _create_project(client, token)

            r = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={
                    "object_name": "Cube",
                    "object_type": "MESH",
                    "blob_hash": "too-short",
                },
                files={
                    "json_file": ("metadata.json", io.BytesIO(b'{}'), "application/json"),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 400
            assert "blob_hash" in r.json()["detail"]

    def test_stage_upload_invalid_json(self):
        """Reject upload with invalid JSON."""
        with TestClient(app) as client:
            token, _ = _register_and_login(client)
            project_id = _create_project(client, token)

            r = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={
                    "object_name": "Cube",
                    "object_type": "MESH",
                    "blob_hash": "c" * 64,
                },
                files={
                    "json_file": ("metadata.json", io.BytesIO(b'not-json'), "application/json"),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 400
            assert "JSON" in r.json()["detail"]

    def test_stage_upload_requires_auth(self):
        """Endpoint requires authentication."""
        with TestClient(app) as client:
            fake_project = str(uuid4())
            r = client.post(
                f"/api/projects/{fake_project}/objects/stage-upload",
                params={
                    "object_name": "Cube",
                    "object_type": "MESH",
                    "blob_hash": "d" * 64,
                },
                files={
                    "json_file": ("metadata.json", io.BytesIO(b'{}'), "application/json"),
                },
            )
            assert r.status_code == 401


class TestFullObjectPushFlow:
    """Integration test: stage-upload objects, then create commit with their paths."""

    def test_upload_then_commit(self):
        """Upload 2 objects via stage-upload, then create commit referencing them."""
        with TestClient(app) as client:
            token, user_id = _register_and_login(client)
            project_id = _create_project(client, token)
            branch_id = _get_main_branch_id(client, token, project_id)
            headers = {"Authorization": f"Bearer {token}"}

            # Upload Cube
            cube_meta = {"object_name": "Cube", "type": "MESH", "transform": {"location": [0, 0, 0]}}
            cube_hash = "1" * 64
            r1 = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={"object_name": "Cube", "object_type": "MESH", "blob_hash": cube_hash},
                files={"json_file": ("m.json", io.BytesIO(json.dumps(cube_meta).encode()), "application/json")},
                headers=headers,
            )
            assert r1.status_code == 201
            cube_paths = r1.json()

            # Upload Camera
            cam_meta = {"object_name": "Camera", "type": "CAMERA", "lens": 50}
            cam_hash = "2" * 64
            r2 = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={"object_name": "Camera", "object_type": "CAMERA", "blob_hash": cam_hash},
                files={"json_file": ("m.json", io.BytesIO(json.dumps(cam_meta).encode()), "application/json")},
                headers=headers,
            )
            assert r2.status_code == 201
            cam_paths = r2.json()

            # Create commit with both objects
            commit_r = client.post(
                f"/api/projects/{project_id}/commits",
                json={
                    "branch_id": branch_id,
                    "commit_message": "Add Cube and Camera",
                    "objects": [
                        {
                            "object_name": "Cube",
                            "object_type": "MESH",
                            "json_data_path": cube_paths["json_path"],
                            "mesh_data_path": None,
                            "blob_hash": cube_hash,
                        },
                        {
                            "object_name": "Camera",
                            "object_type": "CAMERA",
                            "json_data_path": cam_paths["json_path"],
                            "mesh_data_path": None,
                            "blob_hash": cam_hash,
                        },
                    ],
                },
                headers=headers,
            )
            assert commit_r.status_code == 201, commit_r.text
            commit = commit_r.json()
            assert commit["commit_message"] == "Add Cube and Camera"

            # Verify objects are in the commit
            objs_r = client.get(
                f"/api/projects/{project_id}/commits/{commit['commit_id']}/objects",
                headers=headers,
            )
            assert objs_r.status_code == 200
            objects = objs_r.json()
            assert len(objects) == 2
            names = {o["object_name"] for o in objects}
            assert names == {"Cube", "Camera"}


class TestObjectDownloadUrl:

    def test_download_url_for_uploaded_object(self):
        """Get presigned URL for an object previously uploaded via stage-upload."""
        with TestClient(app) as client:
            token, _ = _register_and_login(client)
            project_id = _create_project(client, token)
            headers = {"Authorization": f"Bearer {token}"}

            # Upload an object first
            meta = {"test": "data"}
            r = client.post(
                f"/api/projects/{project_id}/objects/stage-upload",
                params={"object_name": "Test", "object_type": "EMPTY", "blob_hash": "e" * 64},
                files={"json_file": ("m.json", io.BytesIO(json.dumps(meta).encode()), "application/json")},
                headers=headers,
            )
            assert r.status_code == 201
            json_path = r.json()["json_path"]

            # Get presigned download URL
            r = client.get(
                f"/api/projects/{project_id}/objects/download-url",
                params={"path": json_path},
                headers=headers,
            )
            assert r.status_code == 200
            assert "url" in r.json()
            assert r.json()["url"]  # non-empty

    def test_download_url_rejects_wrong_project(self):
        """Reject path that doesn't belong to the project."""
        with TestClient(app) as client:
            token, _ = _register_and_login(client)
            project_id = _create_project(client, token)
            other_project = str(uuid4())

            r = client.get(
                f"/api/projects/{project_id}/objects/download-url",
                params={"path": f"projects/{other_project}/objects/foo/bar.json"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 403

    def test_download_url_requires_auth(self):
        """Endpoint requires authentication."""
        with TestClient(app) as client:
            r = client.get(
                f"/api/projects/{uuid4()}/objects/download-url",
                params={"path": "anything"},
            )
            assert r.status_code == 401
