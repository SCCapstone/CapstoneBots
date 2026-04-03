"""
Functional tests for project, branch, commit, member, and lock endpoints.

Tests the behavior (data correctness, edge cases, error handling) of
routers/projects.py endpoints — complementing test_authorization.py which
tests role-based access control.

Requires a running PostgreSQL database.
Run with: docker compose up -d db && cd backend && pytest tests/test_projects.py -v
"""

import os
import sys
import pytest
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import importlib.util

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)

os.environ.setdefault("JWT_SECRET", "test-secret-for-project-tests")

from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location("main", os.path.join(root, "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
app = main.app

from utils.auth import create_email_verification_token


# --------------- DB availability ---------------

def _db_available():
    try:
        with TestClient(app) as c:
            return c.get("/api/health").status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL database not available (start with: docker compose up -d db)",
)


# --------------- Helpers ---------------

def _verify(client, email):
    token = create_email_verification_token(email)
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text


def _register_and_login(client, prefix="proj"):
    username = f"{prefix}_{uuid4().hex[:8]}"
    email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": "testpass123",
    })
    assert r.status_code == 201, r.text
    user_data = r.json()
    _verify(client, email)
    r = client.post("/api/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return user_data, r.json()["access_token"], email, username


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token, name=None):
    name = name or f"Project {uuid4().hex[:6]}"
    r = client.post("/api/projects", json={"name": name, "description": "test"}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


def _get_main_branch(client, token, project_id):
    r = client.get(f"/api/projects/{project_id}/branches", headers=_h(token))
    assert r.status_code == 200, r.text
    branches = r.json()
    main = [b for b in branches if b["branch_name"] == "main"]
    assert main, "main branch not found"
    return main[0]


def _make_commit(client, token, project_id, branch_id, message="test commit", objects=None):
    objects = objects or [{
        "object_name": f"Obj_{uuid4().hex[:6]}",
        "object_type": "MESH",
        "json_data_path": f"test/{uuid4().hex[:6]}.json",
        "blob_hash": uuid4().hex[:12],
    }]
    r = client.post(
        f"/api/projects/{project_id}/commits",
        json={"branch_id": branch_id, "commit_message": message, "objects": objects},
        headers=_h(token),
    )
    return r


def _invite_and_accept(client, project_id, owner_token, invitee_email, invitee_token, role="editor"):
    r = client.post(
        f"/api/projects/{project_id}/invitations",
        json={"email": invitee_email, "role": role},
        headers=_h(owner_token),
    )
    assert r.status_code == 201, r.text
    inv_id = r.json()["invitation_id"]
    r = client.post(f"/api/auth/invitations/{inv_id}/accept", headers=_h(invitee_token))
    assert r.status_code in (200, 201), r.text
    return inv_id


def _naive_future(hours=1):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(tzinfo=None).isoformat()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# =====================================================================
# Project CRUD
# =====================================================================

class TestProjectCRUD:

    def test_create_project_returns_correct_fields(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token, "My Scene")
        assert proj["name"] == "My Scene"
        assert proj["description"] == "test"
        assert proj["default_branch"] == "main"
        assert proj["active"] is True
        assert "project_id" in proj
        assert "owner_id" in proj

    def test_create_project_auto_creates_main_branch(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        assert main["branch_name"] == "main"

    def test_create_project_adds_owner_as_member(self, client):
        user, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(token))
        assert r.status_code == 200
        members = r.json()
        owner_members = [m for m in members if m["role"] == "owner"]
        assert len(owner_members) == 1
        assert owner_members[0]["user_id"] == user["user_id"]

    def test_get_project_by_id(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.get(f"/api/projects/{proj['project_id']}", headers=_h(token))
        assert r.status_code == 200
        assert r.json()["project_id"] == proj["project_id"]

    def test_get_nonexistent_project_returns_404(self, client):
        _, token, _, _ = _register_and_login(client)
        r = client.get(f"/api/projects/{uuid4()}", headers=_h(token))
        assert r.status_code == 404

    def test_update_project_name(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token, "OldName")
        r = client.put(
            f"/api/projects/{proj['project_id']}",
            json={"name": "NewName"},
            headers=_h(token),
        )
        assert r.status_code == 200
        assert r.json()["name"] == "NewName"
        # description should remain unchanged
        assert r.json()["description"] == "test"

    def test_update_project_partial_fields(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.put(
            f"/api/projects/{proj['project_id']}",
            json={"active": False},
            headers=_h(token),
        )
        assert r.status_code == 200
        assert r.json()["active"] is False
        assert r.json()["name"] == proj["name"]

    def test_delete_project(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        pid = proj["project_id"]
        r = client.delete(f"/api/projects/{pid}", headers=_h(token))
        assert r.status_code == 204
        # Confirm gone
        r = client.get(f"/api/projects/{pid}", headers=_h(token))
        assert r.status_code == 404

    def test_list_projects_returns_owned_and_member_projects(self, client):
        owner_data, owner_token, _, _ = _register_and_login(client)
        _, editor_token, editor_email, _ = _register_and_login(client)

        p1 = _create_project(client, owner_token, "OwnerProj")
        p2 = _create_project(client, editor_token, "EditorOwnedProj")

        # Invite editor into owner's project
        _invite_and_accept(client, p1["project_id"], owner_token, editor_email, editor_token)

        r = client.get("/api/projects", headers=_h(editor_token))
        assert r.status_code == 200
        ids = [p["project_id"] for p in r.json()]
        assert p1["project_id"] in ids  # member of
        assert p2["project_id"] in ids  # owns


# =====================================================================
# Branch endpoints
# =====================================================================

class TestBranches:

    def test_create_branch(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.post(
            f"/api/projects/{proj['project_id']}/branches",
            json={"name": "feature-x"},
            headers=_h(token),
        )
        assert r.status_code == 201
        assert r.json()["branch_name"] == "feature-x"

    def test_create_branch_empty_name_rejected(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.post(
            f"/api/projects/{proj['project_id']}/branches",
            json={"name": "  "},
            headers=_h(token),
        )
        assert r.status_code == 400

    def test_create_branch_with_slash_rejected(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.post(
            f"/api/projects/{proj['project_id']}/branches",
            json={"name": "feat/x"},
            headers=_h(token),
        )
        assert r.status_code == 400

    def test_create_branch_too_long_rejected(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.post(
            f"/api/projects/{proj['project_id']}/branches",
            json={"name": "a" * 256},
            headers=_h(token),
        )
        assert r.status_code == 400

    def test_list_branches_includes_main(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.get(f"/api/projects/{proj['project_id']}/branches", headers=_h(token))
        assert r.status_code == 200
        names = [b["branch_name"] for b in r.json()]
        assert "main" in names

    def test_create_branch_with_parent(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        r = client.post(
            f"/api/projects/{proj['project_id']}/branches",
            json={"name": "child", "parent_branch_id": main["branch_id"]},
            headers=_h(token),
        )
        assert r.status_code == 201


# =====================================================================
# Commit endpoints
# =====================================================================

class TestCommits:

    def test_create_commit_returns_correct_fields(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        r = _make_commit(client, token, proj["project_id"], main["branch_id"], "initial commit")
        assert r.status_code == 201
        c = r.json()
        assert c["commit_message"] == "initial commit"
        assert c["project_id"] == proj["project_id"]
        assert c["branch_id"] == main["branch_id"]
        assert "commit_hash" in c
        assert len(c["commit_hash"]) == 64  # SHA-256

    def test_commit_no_objects_rejected(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        r = client.post(
            f"/api/projects/{proj['project_id']}/commits",
            json={
                "branch_id": main["branch_id"],
                "commit_message": "empty",
                "objects": [],
            },
            headers=_h(token),
        )
        assert r.status_code == 400

    def test_commit_wrong_branch_rejected(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = _make_commit(client, token, proj["project_id"], str(uuid4()), "bad branch")
        assert r.status_code == 404

    def test_commit_history_ordered_newest_first(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        bid = main["branch_id"]

        _make_commit(client, token, proj["project_id"], bid, "first")
        _make_commit(client, token, proj["project_id"], bid, "second")
        _make_commit(client, token, proj["project_id"], bid, "third")

        r = client.get(f"/api/projects/{proj['project_id']}/commits", headers=_h(token))
        assert r.status_code == 200
        messages = [c["commit_message"] for c in r.json()]
        assert messages == ["third", "second", "first"]

    def test_commit_history_nonexistent_branch_returns_empty(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.get(
            f"/api/projects/{proj['project_id']}/commits",
            params={"branch_name": "no-such-branch"},
            headers=_h(token),
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_commit_chain_parent_ids(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        bid = main["branch_id"]

        r1 = _make_commit(client, token, proj["project_id"], bid, "c1")
        c1 = r1.json()
        assert c1["parent_commit_id"] is None  # first commit

        r2 = _make_commit(client, token, proj["project_id"], bid, "c2")
        c2 = r2.json()
        assert c2["parent_commit_id"] == c1["commit_id"]

    def test_get_commit_objects(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        objs = [
            {"object_name": "Cube", "object_type": "MESH", "json_data_path": "a.json", "blob_hash": "h1"},
            {"object_name": "Light", "object_type": "LIGHT", "json_data_path": "b.json", "blob_hash": "h2"},
        ]
        r = _make_commit(client, token, proj["project_id"], main["branch_id"], "with objects", objs)
        assert r.status_code == 201
        cid = r.json()["commit_id"]

        r = client.get(
            f"/api/projects/{proj['project_id']}/commits/{cid}/objects",
            headers=_h(token),
        )
        assert r.status_code == 200
        names = sorted([o["object_name"] for o in r.json()])
        assert names == ["Cube", "Light"]

    def test_commit_updates_branch_head(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])
        bid = main["branch_id"]

        r = _make_commit(client, token, proj["project_id"], bid, "head update")
        cid = r.json()["commit_id"]

        # Re-fetch branch to check head_commit_id
        r = client.get(f"/api/projects/{proj['project_id']}/branches", headers=_h(token))
        updated_main = [b for b in r.json() if b["branch_name"] == "main"][0]
        assert updated_main["head_commit_id"] == cid


# =====================================================================
# Invitation flow: send → accept / decline / cancel
# =====================================================================

class TestInvitationFlow:

    def test_send_invitation(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, _, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 201
        inv = r.json()
        assert inv["role"] == "editor"
        assert inv["status"] == "pending"
        assert inv["invitee_email"] == invitee_email

    def test_accept_invitation_creates_membership(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        invitee_data, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        _invite_and_accept(client, proj["project_id"], owner_token, invitee_email, invitee_token, "viewer")

        # Verify membership
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        user_ids = [m["user_id"] for m in r.json()]
        assert invitee_data["user_id"] in user_ids

    def test_decline_invitation(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        inv_id = r.json()["invitation_id"]

        r = client.post(f"/api/auth/invitations/{inv_id}/decline", headers=_h(invitee_token))
        assert r.status_code == 200
        assert r.json()["status"] == "declined"

    def test_cancel_invitation(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, _, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        inv_id = r.json()["invitation_id"]

        r = client.delete(
            f"/api/projects/{proj['project_id']}/invitations/{inv_id}",
            headers=_h(owner_token),
        )
        assert r.status_code == 204

    def test_cannot_invite_yourself(self, client):
        _, owner_token, owner_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": owner_email, "role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 400

    def test_cannot_invite_existing_member(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        _invite_and_accept(client, proj["project_id"], owner_token, invitee_email, invitee_token)

        # Try inviting again
        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 409

    def test_duplicate_pending_invitation_rejected(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, _, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 201

        # Same invitation again
        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "viewer"},
            headers=_h(owner_token),
        )
        assert r.status_code == 409

    def test_invite_nonexistent_user_rejected(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": "ghost@nowhere.example", "role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 404

    def test_invite_by_username(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, _, _, invitee_username = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"username": invitee_username, "role": "viewer"},
            headers=_h(owner_token),
        )
        assert r.status_code == 201

    def test_invite_with_invalid_role_rejected(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, _, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "superadmin"},
            headers=_h(owner_token),
        )
        assert r.status_code == 400

    def test_editor_cannot_invite_as_owner(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, editor_token, editor_email, _ = _register_and_login(client)
        _, _, target_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        _invite_and_accept(client, proj["project_id"], owner_token, editor_email, editor_token, "editor")

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": target_email, "role": "owner"},
            headers=_h(editor_token),
        )
        assert r.status_code == 403

    def test_pending_invitations_listed_for_invitee(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )

        r = client.get("/api/auth/invitations/pending", headers=_h(invitee_token))
        assert r.status_code == 200
        pids = [i["project_id"] for i in r.json()]
        assert proj["project_id"] in pids

    def test_accept_invitation_by_wrong_user_rejected(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, _, invitee_email, _ = _register_and_login(client)
        _, stranger_token, _, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)

        r = client.post(
            f"/api/projects/{proj['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        inv_id = r.json()["invitation_id"]

        r = client.post(f"/api/auth/invitations/{inv_id}/accept", headers=_h(stranger_token))
        assert r.status_code == 403


# =====================================================================
# Member management
# =====================================================================

class TestMemberManagement:

    def test_list_members_includes_owner(self, client):
        user, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(token))
        assert r.status_code == 200
        roles = {m["role"] for m in r.json()}
        assert "owner" in roles

    def test_update_member_role(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        _invite_and_accept(client, proj["project_id"], owner_token, invitee_email, invitee_token, "viewer")

        # Find the viewer member_id
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        viewer = [m for m in r.json() if m["role"] == "viewer"][0]

        r = client.put(
            f"/api/projects/{proj['project_id']}/members/{viewer['member_id']}/role",
            json={"role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 200
        assert r.json()["role"] == "editor"

    def test_owner_cannot_change_own_role(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        owner_member = [m for m in r.json() if m["role"] == "owner"][0]

        r = client.put(
            f"/api/projects/{proj['project_id']}/members/{owner_member['member_id']}/role",
            json={"role": "editor"},
            headers=_h(owner_token),
        )
        assert r.status_code == 400

    def test_remove_member(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        _invite_and_accept(client, proj["project_id"], owner_token, invitee_email, invitee_token)

        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        editor = [m for m in r.json() if m["role"] == "editor"][0]

        r = client.delete(
            f"/api/projects/{proj['project_id']}/members/{editor['member_id']}",
            headers=_h(owner_token),
        )
        assert r.status_code == 204

        # Confirm removed
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        user_ids = [m["user_id"] for m in r.json()]
        assert editor["user_id"] not in user_ids

    def test_cannot_remove_owner(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        owner_member = [m for m in r.json() if m["role"] == "owner"][0]

        r = client.delete(
            f"/api/projects/{proj['project_id']}/members/{owner_member['member_id']}",
            headers=_h(owner_token),
        )
        assert r.status_code == 409

    def test_update_role_invalid_value_rejected(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        _invite_and_accept(client, proj["project_id"], owner_token, invitee_email, invitee_token)

        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        editor = [m for m in r.json() if m["role"] == "editor"][0]

        r = client.put(
            f"/api/projects/{proj['project_id']}/members/{editor['member_id']}/role",
            json={"role": "superadmin"},
            headers=_h(owner_token),
        )
        assert r.status_code == 400

    def test_remove_nonexistent_member_returns_404(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        r = client.delete(
            f"/api/projects/{proj['project_id']}/members/{uuid4()}",
            headers=_h(owner_token),
        )
        assert r.status_code == 404


# =====================================================================
# Object locking
# =====================================================================

class TestObjectLocking:

    def test_lock_and_list(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])

        r = client.post(
            f"/api/projects/{proj['project_id']}/locks",
            json={"object_name": "Cube", "branch_id": main["branch_id"], "expires_at": _naive_future()},
            headers=_h(token),
        )
        assert r.status_code == 201
        lock = r.json()
        assert lock["object_name"] == "Cube"
        assert "lock_id" in lock

        r = client.get(f"/api/projects/{proj['project_id']}/locks", headers=_h(token))
        assert r.status_code == 200
        assert any(l["lock_id"] == lock["lock_id"] for l in r.json())

    def test_duplicate_lock_rejected(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])

        body = {"object_name": "Cube", "branch_id": main["branch_id"], "expires_at": _naive_future()}
        client.post(f"/api/projects/{proj['project_id']}/locks", json=body, headers=_h(token))
        r = client.post(f"/api/projects/{proj['project_id']}/locks", json=body, headers=_h(token))
        assert r.status_code == 409

    def test_unlock_removes_lock(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])

        r = client.post(
            f"/api/projects/{proj['project_id']}/locks",
            json={"object_name": "Torus", "branch_id": main["branch_id"], "expires_at": _naive_future()},
            headers=_h(token),
        )
        lock_id = r.json()["lock_id"]

        r = client.delete(f"/api/projects/{proj['project_id']}/locks/{lock_id}", headers=_h(token))
        assert r.status_code == 204

        r = client.get(f"/api/projects/{proj['project_id']}/locks", headers=_h(token))
        assert not any(l["lock_id"] == lock_id for l in r.json())

    def test_commit_blocked_by_other_users_lock(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, editor_token, editor_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        main = _get_main_branch(client, owner_token, proj["project_id"])
        _invite_and_accept(client, proj["project_id"], owner_token, editor_email, editor_token)

        # Owner locks Cube
        client.post(
            f"/api/projects/{proj['project_id']}/locks",
            json={"object_name": "Cube", "branch_id": main["branch_id"], "expires_at": _naive_future(2)},
            headers=_h(owner_token),
        )

        # Editor tries to commit Cube — should be blocked
        r = _make_commit(
            client, editor_token, proj["project_id"], main["branch_id"],
            "conflict commit",
            [{"object_name": "Cube", "object_type": "MESH", "json_data_path": "x.json", "blob_hash": "hh"}],
        )
        assert r.status_code == 423

    def test_lock_holder_can_commit_locked_object(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        main = _get_main_branch(client, token, proj["project_id"])

        client.post(
            f"/api/projects/{proj['project_id']}/locks",
            json={"object_name": "Sphere", "branch_id": main["branch_id"], "expires_at": _naive_future(2)},
            headers=_h(token),
        )

        r = _make_commit(
            client, token, proj["project_id"], main["branch_id"],
            "my locked obj",
            [{"object_name": "Sphere", "object_type": "MESH", "json_data_path": "s.json", "blob_hash": "ss"}],
        )
        assert r.status_code == 201

    def test_unlock_nonexistent_returns_404(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.delete(
            f"/api/projects/{proj['project_id']}/locks/{uuid4()}",
            headers=_h(token),
        )
        assert r.status_code == 404


# =====================================================================
# Merge conflicts (read-only — conflict creation is internal)
# =====================================================================

class TestConflicts:

    def test_empty_conflicts_list(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.get(f"/api/projects/{proj['project_id']}/conflicts", headers=_h(token))
        assert r.status_code == 200
        assert r.json() == []

    def test_resolve_nonexistent_conflict_returns_404(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        r = client.put(
            f"/api/projects/{proj['project_id']}/conflicts/{uuid4()}",
            headers=_h(token),
        )
        assert r.status_code == 404


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases:

    def test_removed_member_loses_access(self, client):
        """After being removed, the user should get 403 on project endpoints."""
        _, owner_token, _, _ = _register_and_login(client)
        _, editor_token, editor_email, _ = _register_and_login(client)
        proj = _create_project(client, owner_token)
        _invite_and_accept(client, proj["project_id"], owner_token, editor_email, editor_token)

        # Editor can access
        r = client.get(f"/api/projects/{proj['project_id']}", headers=_h(editor_token))
        assert r.status_code == 200

        # Remove editor
        r = client.get(f"/api/projects/{proj['project_id']}/members", headers=_h(owner_token))
        editor_member = [m for m in r.json() if m["role"] == "editor"][0]
        client.delete(
            f"/api/projects/{proj['project_id']}/members/{editor_member['member_id']}",
            headers=_h(owner_token),
        )

        # Editor can no longer access
        r = client.get(f"/api/projects/{proj['project_id']}", headers=_h(editor_token))
        assert r.status_code == 403

    def test_deleted_project_inaccessible(self, client):
        _, token, _, _ = _register_and_login(client)
        proj = _create_project(client, token)
        pid = proj["project_id"]
        client.delete(f"/api/projects/{pid}", headers=_h(token))

        r = client.get(f"/api/projects/{pid}", headers=_h(token))
        assert r.status_code == 404

        r = client.get(f"/api/projects/{pid}/branches", headers=_h(token))
        assert r.status_code == 404

        r = client.get(f"/api/projects/{pid}/commits", headers=_h(token))
        assert r.status_code == 404
