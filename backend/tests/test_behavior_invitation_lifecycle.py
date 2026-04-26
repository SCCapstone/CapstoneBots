"""
Behavioral tests for invitation lifecycle transitions.

These tests focus on user-visible collaboration behavior across invitation
states (pending, accepted, declined, cancelled).
"""

import pytest

from conftest import (
    requires_db,
    register_and_login as _register_and_login,
    auth_header as _h,
    create_project as _create_project,
)


pytestmark = requires_db


class TestInvitationLifecycle:

    def test_declined_invitation_cannot_be_accepted_later(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        project = _create_project(client, owner_token)

        invite_resp = client.post(
            f"/api/projects/{project['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        assert invite_resp.status_code == 201
        invitation_id = invite_resp.json()["invitation_id"]

        decline_resp = client.post(
            f"/api/auth/invitations/{invitation_id}/decline",
            headers=_h(invitee_token),
        )
        assert decline_resp.status_code == 200

        accept_after_decline = client.post(
            f"/api/auth/invitations/{invitation_id}/accept",
            headers=_h(invitee_token),
        )
        assert accept_after_decline.status_code == 400
        assert "already declined" in accept_after_decline.json()["detail"].lower()

    def test_cancelled_invitation_is_not_actionable(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        project = _create_project(client, owner_token)

        invite_resp = client.post(
            f"/api/projects/{project['project_id']}/invitations",
            json={"email": invitee_email, "role": "viewer"},
            headers=_h(owner_token),
        )
        assert invite_resp.status_code == 201
        invitation_id = invite_resp.json()["invitation_id"]

        cancel_resp = client.delete(
            f"/api/projects/{project['project_id']}/invitations/{invitation_id}",
            headers=_h(owner_token),
        )
        assert cancel_resp.status_code == 204

        accept_after_cancel = client.post(
            f"/api/auth/invitations/{invitation_id}/accept",
            headers=_h(invitee_token),
        )
        assert accept_after_cancel.status_code == 404

    def test_accepted_invitation_disappears_from_pending_list(self, client):
        _, owner_token, _, _ = _register_and_login(client)
        _, invitee_token, invitee_email, _ = _register_and_login(client)
        project = _create_project(client, owner_token)

        invite_resp = client.post(
            f"/api/projects/{project['project_id']}/invitations",
            json={"email": invitee_email, "role": "editor"},
            headers=_h(owner_token),
        )
        assert invite_resp.status_code == 201
        invitation_id = invite_resp.json()["invitation_id"]

        pending_before = client.get("/api/auth/invitations/pending", headers=_h(invitee_token))
        assert pending_before.status_code == 200
        pending_ids_before = {item["invitation_id"] for item in pending_before.json()}
        assert invitation_id in pending_ids_before

        accept_resp = client.post(
            f"/api/auth/invitations/{invitation_id}/accept",
            headers=_h(invitee_token),
        )
        assert accept_resp.status_code == 200

        pending_after = client.get("/api/auth/invitations/pending", headers=_h(invitee_token))
        assert pending_after.status_code == 200
        pending_ids_after = {item["invitation_id"] for item in pending_after.json()}
        assert invitation_id not in pending_ids_after
