"""
Unit Tests for Models (backend/models.py)

Tests the role hierarchy enum, role_at_least helper, and model defaults.
These are pure unit tests — no database required.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")

from models import MemberRole, role_at_least, InvitationStatus, ROLE_HIERARCHY, INVITE_EXPIRY_DAYS


# ============== Role Hierarchy ==============

class TestRoleHierarchy:
    """Tests for the MemberRole enum and role_at_least helper."""

    def test_role_values(self):
        """Enum values match expected strings."""
        assert MemberRole.viewer.value == "viewer"
        assert MemberRole.editor.value == "editor"
        assert MemberRole.owner.value == "owner"

    def test_hierarchy_ordering(self):
        """viewer < editor < owner in ROLE_HIERARCHY."""
        assert ROLE_HIERARCHY[MemberRole.viewer] < ROLE_HIERARCHY[MemberRole.editor]
        assert ROLE_HIERARCHY[MemberRole.editor] < ROLE_HIERARCHY[MemberRole.owner]

    def test_role_at_least_viewer_meets_viewer(self):
        assert role_at_least(MemberRole.viewer, MemberRole.viewer) is True

    def test_role_at_least_editor_meets_viewer(self):
        assert role_at_least(MemberRole.editor, MemberRole.viewer) is True

    def test_role_at_least_owner_meets_editor(self):
        assert role_at_least(MemberRole.owner, MemberRole.editor) is True

    def test_role_at_least_owner_meets_owner(self):
        assert role_at_least(MemberRole.owner, MemberRole.owner) is True

    def test_role_at_least_viewer_does_not_meet_editor(self):
        assert role_at_least(MemberRole.viewer, MemberRole.editor) is False

    def test_role_at_least_viewer_does_not_meet_owner(self):
        assert role_at_least(MemberRole.viewer, MemberRole.owner) is False

    def test_role_at_least_editor_does_not_meet_owner(self):
        assert role_at_least(MemberRole.editor, MemberRole.owner) is False


# ============== InvitationStatus ==============

class TestInvitationStatus:
    """Tests for the InvitationStatus enum."""

    def test_status_values(self):
        assert InvitationStatus.pending.value == "pending"
        assert InvitationStatus.accepted.value == "accepted"
        assert InvitationStatus.declined.value == "declined"
        assert InvitationStatus.expired.value == "expired"

    def test_all_statuses_present(self):
        """All four statuses are defined."""
        statuses = [s.value for s in InvitationStatus]
        assert set(statuses) == {"pending", "accepted", "declined", "expired"}


# ============== Invite Expiry ==============

class TestInviteExpiry:
    """Tests for INVITE_EXPIRY_DAYS default."""

    def test_default_expiry_days(self):
        """Default invite expiry should be 7 days (from env or fallback)."""
        assert isinstance(INVITE_EXPIRY_DAYS, int)
        assert INVITE_EXPIRY_DAYS > 0


# ============== MemberRole from string ==============

class TestMemberRoleFromString:
    """Tests for creating MemberRole from string values."""

    def test_valid_role_from_string(self):
        assert MemberRole("viewer") == MemberRole.viewer
        assert MemberRole("editor") == MemberRole.editor
        assert MemberRole("owner") == MemberRole.owner

    def test_invalid_role_from_string_raises(self):
        with pytest.raises(ValueError):
            MemberRole("admin")

    def test_invalid_role_empty_string_raises(self):
        with pytest.raises(ValueError):
            MemberRole("")
