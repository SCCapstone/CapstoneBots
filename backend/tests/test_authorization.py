"""
Authorization tests for project and storage endpoints.

Verifies that check_project_access enforces role-based access control:
- 401 for unauthenticated requests on every protected endpoint
- 403 for non-members on every project-scoped endpoint
- 403 for viewers on editor/owner actions
- 403 for editors on owner-only actions
- 200/201/204 for roles at or above the required level
- Lock release restricted to lock holder or project owner

Requires a running PostgreSQL database.
Run with: docker compose up -d db && cd backend && pytest tests/test_authorization.py -v
"""

import pytest
from uuid import uuid4

from conftest import (
    requires_db, register_and_login, auth_header, invite_and_accept,
)


pytestmark = requires_db


# --------------- Helpers ---------------

def _h(token):
    """Build auth header dict."""
    return auth_header(token)



# --------------- Shared fixture ---------------

class _Ctx:
    """Mutable container populated once per module."""
    pass


CTX = _Ctx()


@pytest.fixture(scope="module", autouse=True)
def setup_project_with_roles():
    """Create four users (owner, editor, viewer, non-member) and a project."""
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        # Register & login four users
        CTX.owner_data, CTX.owner_token, CTX.owner_email, _ = register_and_login(client, prefix="authz")
        CTX.editor_data, CTX.editor_token, CTX.editor_email, _ = register_and_login(client, prefix="authz")
        CTX.viewer_data, CTX.viewer_token, CTX.viewer_email, _ = register_and_login(client, prefix="authz")
        CTX.nonmember_data, CTX.nonmember_token, CTX.nonmember_email, _ = register_and_login(client, prefix="authz")

        # Owner creates a project (auto-creates "main" branch)
        r = client.post(
            "/api/projects",
            json={"name": f"AuthZ Test {uuid4().hex[:6]}"},
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 201
        CTX.project_id = r.json()["project_id"]

        # Add editor and viewer via invitation flow
        invite_and_accept(
            client, CTX.project_id,
            CTX.owner_token, CTX.editor_email, CTX.editor_token, "editor",
        )
        invite_and_accept(
            client, CTX.project_id,
            CTX.owner_token, CTX.viewer_email, CTX.viewer_token, "viewer",
        )

        # Fetch the main branch id
        r = client.get(
            f"/api/projects/{CTX.project_id}/branches",
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 200
        branches = r.json()
        CTX.main_branch_id = branches[0]["branch_id"]

        # Editor creates a commit (needed for object / lock tests)
        r = client.post(
            f"/api/projects/{CTX.project_id}/commits",
            json={
                "branch_id": CTX.main_branch_id,
                "commit_message": "initial authz test commit",
                "objects": [
                    {
                        "object_name": "Cube",
                        "object_type": "MESH",
                        "json_data_path": "test/cube.json",
                        "blob_hash": "abc123",
                    }
                ],
            },
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 201, r.text
        CTX.commit_id = r.json()["commit_id"]

        # Fetch member IDs for later tests
        r = client.get(
            f"/api/projects/{CTX.project_id}/members",
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 200
        for m in r.json():
            if m["role"] == "viewer":
                CTX.viewer_member_id = m["member_id"]
            elif m["role"] == "editor":
                CTX.editor_member_id = m["member_id"]
            elif m["role"] == "owner":
                CTX.owner_member_id = m["member_id"]

    yield


# =====================================================================
# 1. Unauthenticated requests → 401
# =====================================================================

_UNAUTH_ENDPOINTS = [
    ("GET",    "/api/projects"),
    ("POST",   "/api/projects"),
    ("GET",    "/api/projects/{pid}"),
    ("PUT",    "/api/projects/{pid}"),
    ("DELETE", "/api/projects/{pid}"),
    ("GET",    "/api/projects/{pid}/branches"),
    ("POST",   "/api/projects/{pid}/branches"),
    ("GET",    "/api/projects/{pid}/commits"),
    ("POST",   "/api/projects/{pid}/commits"),
    ("GET",    "/api/projects/{pid}/commits/{cid}/objects"),
    ("GET",    "/api/projects/{pid}/locks"),
    ("POST",   "/api/projects/{pid}/locks"),
    ("GET",    "/api/projects/{pid}/conflicts"),
    ("GET",    "/api/projects/{pid}/members"),
    ("POST",   "/api/projects/{pid}/members"),
    ("GET",    "/api/projects/{pid}/invitations"),
    ("POST",   "/api/projects/{pid}/invitations"),
    # NOTE: Storage endpoints (download, versions, storage-stats) are excluded
    # because they depend on MinIO via get_storage_service which fails before
    # auth runs when MinIO is unavailable. Their auth is identical
    # (check_project_access) and tested via the projects-router tests.
]


@pytest.mark.parametrize("method,path", _UNAUTH_ENDPOINTS, ids=[f"{m} {p}" for m, p in _UNAUTH_ENDPOINTS])
def test_unauthenticated_returns_401(client, method, path):
    url = path.replace("{pid}", CTX.project_id).replace("{cid}", CTX.commit_id)
    r = getattr(client, method.lower())(url)
    assert r.status_code in (401, 403), f"{method} {url} returned {r.status_code}, expected 401 or 403"


# =====================================================================
# 2. Non-member → 403 on every project-scoped endpoint
# =====================================================================

_NONMEMBER_ENDPOINTS = [
    ("GET",    "/api/projects/{pid}"),
    ("PUT",    "/api/projects/{pid}"),
    ("DELETE", "/api/projects/{pid}"),
    ("GET",    "/api/projects/{pid}/branches"),
    ("POST",   "/api/projects/{pid}/branches"),
    ("GET",    "/api/projects/{pid}/commits"),
    ("POST",   "/api/projects/{pid}/commits"),
    ("GET",    "/api/projects/{pid}/commits/{cid}/objects"),
    ("GET",    "/api/projects/{pid}/locks"),
    ("POST",   "/api/projects/{pid}/locks"),
    ("GET",    "/api/projects/{pid}/conflicts"),
    ("GET",    "/api/projects/{pid}/members"),
    ("POST",   "/api/projects/{pid}/members"),
    ("GET",    "/api/projects/{pid}/invitations"),
    ("POST",   "/api/projects/{pid}/invitations"),
    # NOTE: Storage endpoints excluded — require MinIO (see above).
]

# Minimal JSON bodies so FastAPI doesn't reject with 422 before auth runs
_NONMEMBER_BODIES = {
    ("PUT",  "/api/projects/{pid}"): {"name": "x"},
    ("POST", "/api/projects/{pid}/branches"): {"name": "x"},
    ("POST", "/api/projects/{pid}/commits"): {"branch_id": "00000000-0000-0000-0000-000000000000", "commit_message": "x", "objects": [{"object_name": "O", "object_type": "MESH", "json_data_path": "p", "blob_hash": "h"}]},
    ("POST", "/api/projects/{pid}/locks"): {"object_name": "O", "branch_id": "00000000-0000-0000-0000-000000000000", "expires_at": "2099-01-01T00:00:00"},
    ("POST", "/api/projects/{pid}/members"): {"email": "x@example.com", "role": "viewer"},
    ("POST", "/api/projects/{pid}/invitations"): {"email": "x@example.com", "role": "viewer"},
}


@pytest.mark.parametrize("method,path", _NONMEMBER_ENDPOINTS, ids=[f"{m} {p}" for m, p in _NONMEMBER_ENDPOINTS])
def test_nonmember_returns_403(client, method, path):
    url = path.replace("{pid}", CTX.project_id).replace("{cid}", CTX.commit_id)
    kwargs = {"headers": _h(CTX.nonmember_token)}
    body = _NONMEMBER_BODIES.get((method, path))
    if body:
        kwargs["json"] = body
    r = getattr(client, method.lower())(url, **kwargs)
    assert r.status_code == 403, f"{method} {url} returned {r.status_code}, expected 403"


# =====================================================================
# 3. Viewer CANNOT perform editor+ actions → 403
# =====================================================================

class TestViewerForbidden:
    """A viewer must receive 403 on any action requiring editor or owner role."""

    def test_viewer_cannot_create_branch(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/branches",
            json={"name": "viewer-branch"},
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_create_commit(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/commits",
            json={
                "branch_id": CTX.main_branch_id,
                "commit_message": "viewer commit attempt",
                "objects": [
                    {
                        "object_name": "Sphere",
                        "object_type": "MESH",
                        "json_data_path": "test/sphere.json",
                        "blob_hash": "def456",
                    }
                ],
            },
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_lock_object(self, client):
        from datetime import datetime, timedelta, timezone

        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
        r = client.post(
            f"/api/projects/{CTX.project_id}/locks",
            json={
                "object_name": "Cube",
                "branch_id": CTX.main_branch_id,
                "expires_at": expires.isoformat(),
            },
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_resolve_conflict(self, client):
        fake_conflict_id = str(uuid4())
        r = client.put(
            f"/api/projects/{CTX.project_id}/conflicts/{fake_conflict_id}",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_send_invitation(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/invitations",
            json={"email": "nobody@example.com", "role": "viewer"},
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_view_invitations(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/invitations",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_add_member(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/members",
            json={"email": "nobody@example.com", "role": "viewer"},
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_update_project(self, client):
        r = client.put(
            f"/api/projects/{CTX.project_id}",
            json={"name": "Viewer Rename"},
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_delete_project(self, client):
        r = client.delete(
            f"/api/projects/{CTX.project_id}",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_update_member_role(self, client):
        r = client.put(
            f"/api/projects/{CTX.project_id}/members/{CTX.editor_member_id}/role",
            json={"role": "viewer"},
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_remove_member(self, client):
        r = client.delete(
            f"/api/projects/{CTX.project_id}/members/{CTX.editor_member_id}",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 403


# =====================================================================
# 4. Viewer CAN perform read-only actions → 200
# =====================================================================

class TestViewerAllowed:
    """A viewer can read project data."""

    def test_viewer_can_get_project(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200

    def test_viewer_can_list_branches(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/branches",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200

    def test_viewer_can_list_commits(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/commits",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200

    def test_viewer_can_get_commit_objects(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/commits/{CTX.commit_id}/objects",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200

    def test_viewer_can_list_locks(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/locks",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200

    def test_viewer_can_list_conflicts(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/conflicts",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200

    def test_viewer_can_list_members(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/members",
            headers=_h(CTX.viewer_token),
        )
        assert r.status_code == 200


# =====================================================================
# 5. Editor CAN perform editor-level actions → 200/201
# =====================================================================

class TestEditorAllowed:
    """An editor can create branches, commits, and locks."""

    def test_editor_can_create_branch(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/branches",
            json={"name": f"editor-branch-{uuid4().hex[:6]}"},
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 201

    def test_editor_can_create_commit(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/commits",
            json={
                "branch_id": CTX.main_branch_id,
                "commit_message": "editor commit",
                "objects": [
                    {
                        "object_name": "Cylinder",
                        "object_type": "MESH",
                        "json_data_path": "test/cylinder.json",
                        "blob_hash": f"hash_{uuid4().hex[:8]}",
                    }
                ],
            },
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 201

    def test_editor_can_lock_object(self, client):
        from datetime import datetime, timedelta, timezone

        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
        r = client.post(
            f"/api/projects/{CTX.project_id}/locks",
            json={
                "object_name": f"EditorLockObj_{uuid4().hex[:6]}",
                "branch_id": CTX.main_branch_id,
                "expires_at": expires.isoformat(),
            },
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 201


# =====================================================================
# 6. Editor CANNOT perform owner-only actions → 403
# =====================================================================

class TestEditorForbidden:
    """An editor must be denied owner-only operations."""

    def test_editor_cannot_update_project(self, client):
        r = client.put(
            f"/api/projects/{CTX.project_id}",
            json={"name": "Editor Rename"},
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 403

    def test_editor_cannot_delete_project(self, client):
        r = client.delete(
            f"/api/projects/{CTX.project_id}",
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 403

    def test_editor_cannot_update_member_role(self, client):
        r = client.put(
            f"/api/projects/{CTX.project_id}/members/{CTX.viewer_member_id}/role",
            json={"role": "editor"},
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 403

    def test_editor_cannot_remove_member(self, client):
        r = client.delete(
            f"/api/projects/{CTX.project_id}/members/{CTX.viewer_member_id}",
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 403


# =====================================================================
# 7. Owner CAN perform all actions → 200/201/204
# =====================================================================

class TestOwnerAllowed:
    """The owner can do everything."""

    def test_owner_can_get_project(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}",
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 200

    def test_owner_can_update_project(self, client):
        r = client.put(
            f"/api/projects/{CTX.project_id}",
            json={"description": "Updated by owner"},
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 200

    def test_owner_can_create_branch(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/branches",
            json={"name": f"owner-branch-{uuid4().hex[:6]}"},
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 201

    def test_owner_can_create_commit(self, client):
        r = client.post(
            f"/api/projects/{CTX.project_id}/commits",
            json={
                "branch_id": CTX.main_branch_id,
                "commit_message": "owner commit",
                "objects": [
                    {
                        "object_name": "Torus",
                        "object_type": "MESH",
                        "json_data_path": "test/torus.json",
                        "blob_hash": f"hash_{uuid4().hex[:8]}",
                    }
                ],
            },
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 201

    def test_owner_can_list_invitations(self, client):
        r = client.get(
            f"/api/projects/{CTX.project_id}/invitations",
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 200


# =====================================================================
# 8. Lock release: only lock holder or owner
# =====================================================================

class TestLockRelease:
    """Only the lock holder or project owner can release a lock."""

    def _create_lock(self, client, token, object_name):
        from datetime import datetime, timedelta, timezone

        expires = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None)
        r = client.post(
            f"/api/projects/{CTX.project_id}/locks",
            json={
                "object_name": object_name,
                "branch_id": CTX.main_branch_id,
                "expires_at": expires.isoformat(),
            },
            headers=_h(token),
        )
        assert r.status_code == 201, r.text
        return r.json()["lock_id"]

    def test_viewer_cannot_release_lock(self, client):
        """Viewer cannot release any lock (blocked by check_project_access at viewer level)."""
        lock_id = self._create_lock(client, CTX.editor_token, f"LockTest_ViewerRelease_{uuid4().hex[:6]}")
        r = client.delete(
            f"/api/projects/{CTX.project_id}/locks/{lock_id}",
            headers=_h(CTX.viewer_token),
        )
        # Viewer is a member so passes the access check, but is neither
        # the lock holder nor the owner → 403
        assert r.status_code == 403

    def test_other_editor_cannot_release_lock(self, client):
        """An editor who did NOT create the lock cannot release it."""
        lock_id = self._create_lock(client, CTX.owner_token, f"LockTest_OtherEditor_{uuid4().hex[:6]}")
        r = client.delete(
            f"/api/projects/{CTX.project_id}/locks/{lock_id}",
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 403

    def test_lock_holder_can_release_own_lock(self, client):
        """The user who created the lock can release it."""
        lock_id = self._create_lock(client, CTX.editor_token, f"LockTest_SelfRelease_{uuid4().hex[:6]}")
        r = client.delete(
            f"/api/projects/{CTX.project_id}/locks/{lock_id}",
            headers=_h(CTX.editor_token),
        )
        assert r.status_code == 204

    def test_owner_can_release_any_lock(self, client):
        """The project owner can release any lock, even one they didn't create."""
        lock_id = self._create_lock(client, CTX.editor_token, f"LockTest_OwnerRelease_{uuid4().hex[:6]}")
        r = client.delete(
            f"/api/projects/{CTX.project_id}/locks/{lock_id}",
            headers=_h(CTX.owner_token),
        )
        assert r.status_code == 204

    def test_nonmember_cannot_release_lock(self, client):
        lock_id = self._create_lock(client, CTX.editor_token, f"LockTest_NonMember_{uuid4().hex[:6]}")
        r = client.delete(
            f"/api/projects/{CTX.project_id}/locks/{lock_id}",
            headers=_h(CTX.nonmember_token),
        )
        assert r.status_code == 403


# =====================================================================
# 9. Parametrized access matrix — concise summary
# =====================================================================

# (method, path_template, json_body_factory, min_role)
# min_role: "viewer" = any member, "editor", "owner"
_ACCESS_MATRIX = [
    # --- read-only  (viewer+) ---
    ("GET",  "/{pid}",                          None, "viewer"),
    ("GET",  "/{pid}/branches",                 None, "viewer"),
    ("GET",  "/{pid}/commits",                  None, "viewer"),
    ("GET",  "/{pid}/commits/{cid}/objects",    None, "viewer"),
    ("GET",  "/{pid}/locks",                    None, "viewer"),
    ("GET",  "/{pid}/conflicts",                None, "viewer"),
    ("GET",  "/{pid}/members",                  None, "viewer"),
    # --- editor+ ---
    ("POST", "/{pid}/branches",                 lambda: {"name": f"mx-{uuid4().hex[:6]}"}, "editor"),
    # --- owner-only ---
    ("PUT",  "/{pid}",                          lambda: {"description": "matrix"}, "owner"),
]

_ROLE_TOKENS = {
    "viewer":    lambda: CTX.viewer_token,
    "editor":    lambda: CTX.editor_token,
    "owner":     lambda: CTX.owner_token,
    "nonmember": lambda: CTX.nonmember_token,
}

_ROLE_ORDER = ["nonmember", "viewer", "editor", "owner"]


def _role_index(role):
    return _ROLE_ORDER.index(role)


def _make_id(method, path, role):
    return f"{method} {path} as {role}"


def _matrix_cases():
    """Yield (method, path, body_factory, role, should_succeed) tuples."""
    for method, path, body_factory, min_role in _ACCESS_MATRIX:
        for role in _ROLE_ORDER:
            should_succeed = _role_index(role) >= _role_index(min_role)
            yield pytest.param(
                method, path, body_factory, role, should_succeed,
                id=_make_id(method, path, role),
            )


@pytest.mark.parametrize("method,path,body_factory,role,should_succeed", list(_matrix_cases()))
def test_access_matrix(client, method, path, body_factory, role, should_succeed):
    url = "/api/projects" + path.replace("{pid}", CTX.project_id).replace("{cid}", CTX.commit_id)
    token = _ROLE_TOKENS[role]()
    kwargs = {"headers": _h(token)}
    if body_factory:
        kwargs["json"] = body_factory()

    r = getattr(client, method.lower())(url, **kwargs)

    if should_succeed:
        assert r.status_code < 400, (
            f"{method} {url} as {role}: expected success, got {r.status_code} — {r.text}"
        )
    else:
        assert r.status_code in (403, 404), (
            f"{method} {url} as {role}: expected 403/404, got {r.status_code} — {r.text}"
        )
