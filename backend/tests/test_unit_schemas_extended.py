"""
Extended Unit Tests for Pydantic Schemas (backend/schemas.py)

Covers boundary conditions, optional fields, invalid data, and edge cases.
"""

import os
import pytest
from uuid import uuid4
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")

from schemas import (
    ProjectCreate,
    ProjectUpdate,
    BranchCreate,
    CommitCreateRequest,
    BlenderObjectCreate,
    UserCreate,
    UserLogin,
    Token,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    ResendVerificationRequest,
    ObjectLockCreate,
    StorageObjectInfo,
    ProjectStorageStats,
)


# ============== UserCreate ==============

class TestUserCreateSchema:
    def test_valid_user(self):
        u = UserCreate(username="alice", email="alice@example.com", password="secret123")
        assert u.username == "alice"
        assert u.email == "alice@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(Exception):
            UserCreate(username="alice", email="not-an-email", password="secret123")

    def test_missing_password_rejected(self):
        with pytest.raises(Exception):
            UserCreate(username="alice", email="alice@example.com")

    def test_empty_username(self):
        """Framework allows empty string but that may be caught by backend validation."""
        u = UserCreate(username="", email="a@b.com", password="12345678")
        assert u.username == ""


# ============== UserLogin ==============

class TestUserLoginSchema:
    def test_valid_login(self):
        login = UserLogin(email="user@example.com", password="pass1234")
        assert login.email == "user@example.com"

    def test_invalid_email(self):
        with pytest.raises(Exception):
            UserLogin(email="bad-email", password="pass")


# ============== Token ==============

class TestTokenSchema:
    def test_valid_token(self):
        t = Token(access_token="abc.def.ghi", token_type="bearer")
        assert t.token_type == "bearer"


# ============== ProjectCreate ==============

class TestProjectCreateSchema:
    def test_defaults(self):
        p = ProjectCreate(name="MyProject")
        assert p.active is True
        assert p.description is None

    def test_with_description(self):
        p = ProjectCreate(name="MyProject", description="test desc", active=False)
        assert p.description == "test desc"
        assert p.active is False

    def test_missing_name_rejected(self):
        with pytest.raises(Exception):
            ProjectCreate()

    def test_empty_name(self):
        """Empty name is allowed by schema (backend logic should catch)."""
        p = ProjectCreate(name="")
        assert p.name == ""

    def test_very_long_name(self):
        """Long names are allowed at the schema level."""
        p = ProjectCreate(name="A" * 1000)
        assert len(p.name) == 1000


# ============== ProjectUpdate ==============

class TestProjectUpdateSchema:
    def test_all_none(self):
        """All fields are optional — empty update is valid."""
        u = ProjectUpdate()
        assert u.name is None
        assert u.description is None
        assert u.active is None

    def test_partial_update(self):
        u = ProjectUpdate(name="New Name")
        assert u.name == "New Name"
        assert u.description is None


# ============== BranchCreate ==============

class TestBranchCreateSchema:
    def test_valid_branch(self):
        b = BranchCreate(branch_name="feature/new-mesh")
        assert b.branch_name == "feature/new-mesh"
        assert b.source_commit_id is None

    def test_with_source_commit(self):
        cid = uuid4()
        b = BranchCreate(branch_name="hotfix", source_commit_id=cid)
        assert b.source_commit_id == cid

    def test_missing_name_rejected(self):
        with pytest.raises(Exception):
            BranchCreate()


# ============== CommitCreateRequest ==============

class TestCommitCreateRequestSchema:
    def test_empty_objects_list(self):
        """Commit with zero objects is valid at schema level."""
        c = CommitCreateRequest(
            branch_id=uuid4(),
            commit_message="Empty commit",
            objects=[],
        )
        assert len(c.objects) == 0

    def test_with_objects(self):
        obj = BlenderObjectCreate(
            object_name="Cube",
            object_type="MESH",
            json_data_path="s3://bucket/cube.json",
            blob_hash="abc123",
        )
        c = CommitCreateRequest(
            branch_id=uuid4(),
            commit_message="Add cube",
            objects=[obj],
        )
        assert len(c.objects) == 1
        assert c.objects[0].object_name == "Cube"

    def test_missing_branch_id_allowed(self):
        c = CommitCreateRequest(commit_message="no branch", objects=[])
        assert c.branch_id is None

    def test_missing_message_rejected(self):
        with pytest.raises(Exception):
            CommitCreateRequest(branch_id=uuid4(), objects=[])


# ============== BlenderObjectCreate ==============

class TestBlenderObjectCreateSchema:
    def test_minimal(self):
        obj = BlenderObjectCreate(
            object_name="Cube",
            object_type="MESH",
            json_data_path="path/to/file.json",
            blob_hash="hash123",
        )
        assert obj.mesh_data_path is None
        assert obj.parent_object_id is None

    def test_with_optional_fields(self):
        obj = BlenderObjectCreate(
            object_name="Sphere",
            object_type="MESH",
            json_data_path="path/sphere.json",
            blob_hash="hash456",
            mesh_data_path="path/sphere.bin",
            parent_object_id=uuid4(),
        )
        assert obj.mesh_data_path is not None
        assert obj.parent_object_id is not None

    def test_missing_blob_hash_rejected(self):
        with pytest.raises(Exception):
            BlenderObjectCreate(
                object_name="Cube",
                object_type="MESH",
                json_data_path="path/file.json",
            )


# ============== DeleteAccountRequest ==============

class TestDeleteAccountRequestSchema:
    def test_valid(self):
        d = DeleteAccountRequest(password="mypassword")
        assert d.password == "mypassword"

    def test_missing_password_rejected(self):
        with pytest.raises(Exception):
            DeleteAccountRequest()


# ============== ForgotPasswordRequest ==============

class TestForgotPasswordRequestSchema:
    def test_valid(self):
        f = ForgotPasswordRequest(email="user@example.com")
        assert f.email == "user@example.com"

    def test_invalid_email(self):
        with pytest.raises(Exception):
            ForgotPasswordRequest(email="not-an-email")


# ============== ResetPasswordRequest ==============

class TestResetPasswordRequestSchema:
    def test_valid(self):
        r = ResetPasswordRequest(token="some.jwt.token", new_password="newpass123")
        assert r.new_password == "newpass123"


# ============== VerifyEmailRequest ==============

class TestVerifyEmailRequestSchema:
    def test_valid(self):
        v = VerifyEmailRequest(token="verify.jwt.token")
        assert v.token == "verify.jwt.token"


# ============== ResendVerificationRequest ==============

class TestResendVerificationRequestSchema:
    def test_valid(self):
        r = ResendVerificationRequest(email="user@example.com")
        assert r.email == "user@example.com"


# ============== ObjectLockCreate ==============

class TestObjectLockCreateSchema:
    def test_valid(self):
        lock = ObjectLockCreate(
            object_name="Cube",
            expires_at=datetime.now(timezone.utc),
            branch_id=uuid4(),
        )
        assert lock.object_name == "Cube"


# ============== StorageObjectInfo ==============

class TestStorageObjectInfoSchema:
    def test_valid(self):
        info = StorageObjectInfo(
            name="cube.json",
            size=2048,
            etag="abc123",
            last_modified=datetime.now(timezone.utc),
        )
        assert info.size == 2048
        assert info.version_id is None

    def test_zero_size(self):
        info = StorageObjectInfo(
            name="empty.json",
            size=0,
            etag="d41d8cd98f",
            last_modified=datetime.now(timezone.utc),
        )
        assert info.size == 0


# ============== ProjectStorageStats ==============

class TestProjectStorageStatsSchema:
    def test_valid(self):
        stats = ProjectStorageStats(
            project_id=uuid4(),
            total_bytes=1048576,
            objects_bytes=524288,
            versions_bytes=524288,
            total_mb=1.0,
        )
        assert stats.total_mb == 1.0

    def test_zero_storage(self):
        stats = ProjectStorageStats(
            project_id=uuid4(),
            total_bytes=0,
            objects_bytes=0,
            versions_bytes=0,
            total_mb=0.0,
        )
        assert stats.total_bytes == 0
