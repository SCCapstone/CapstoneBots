from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, Index, LargeBinary, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid
from datetime import datetime, timedelta, timezone
import enum
import os


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (UTC, no tzinfo).

    Columns are TIMESTAMP WITHOUT TIME ZONE so asyncpg requires naive datetimes.
    Using datetime.now(timezone.utc).replace(tzinfo=None) instead of the
    deprecated datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============== Role & Status Enums ==============

class MemberRole(str, enum.Enum):
    """Role hierarchy: owner > editor > viewer"""
    viewer = "viewer"
    editor = "editor"
    owner = "owner"

ROLE_HIERARCHY = {MemberRole.viewer: 0, MemberRole.editor: 1, MemberRole.owner: 2}

def role_at_least(user_role: MemberRole, required: MemberRole) -> bool:
    """Check if user_role meets the minimum required level."""
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(required, 99)


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


INVITE_EXPIRY_DAYS = int(os.getenv("INVITE_EXPIRY_DAYS", "7"))

class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    last_login = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False, server_default="false")
    email_verified_at = Column(DateTime, nullable=True)

    projects = relationship("Project", back_populates="owner")
    commits = relationship("Commit", back_populates="author")
    locks = relationship("ObjectLock", back_populates="locked_by_user")
    project_memberships = relationship("ProjectMember", foreign_keys="ProjectMember.user_id", back_populates="user")
    invitations_sent = relationship("ProjectInvitation", foreign_keys="ProjectInvitation.inviter_id", back_populates="inviter", passive_deletes=True)
    invitations_received = relationship("ProjectInvitation", foreign_keys="ProjectInvitation.invitee_id", back_populates="invitee", passive_deletes=True)


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    default_branch = Column(String, default="main")
    active = Column(Boolean, default=True)

    owner = relationship("User", back_populates="projects")
    branches = relationship("Branch", back_populates="project", cascade="all, delete-orphan")
    commits = relationship("Commit", back_populates="project", cascade="all, delete-orphan")
    locks = relationship("ObjectLock", back_populates="project", cascade="all, delete-orphan")
    project_metadata = relationship("ProjectMetadata", back_populates="project", cascade="all, delete-orphan")
    invitations = relationship("ProjectInvitation", back_populates="project", cascade="all, delete-orphan")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"

    branch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    branch_name = Column(String, nullable=False)
    head_commit_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=True)
    parent_branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "branch_name", name="unique_project_branch"),)

    project = relationship("Project", back_populates="branches")
    head_commit = relationship("Commit", foreign_keys=[head_commit_id])
    parent_branch = relationship("Branch", remote_side=[branch_id])
    commits = relationship("Commit", back_populates="branch", foreign_keys="Commit.branch_id")


class Commit(Base):
    __tablename__ = "commits"

    commit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=True)
    parent_commit_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    commit_message = Column(Text, nullable=False)
    commit_hash = Column(String, unique=True, nullable=False, index=True)
    committed_at = Column(DateTime, default=_utcnow)
    merge_commit = Column(Boolean, default=False)
    merge_parent_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=True)

    project = relationship("Project", back_populates="commits")
    branch = relationship("Branch", back_populates="commits", foreign_keys=[branch_id])
    author = relationship("User", back_populates="commits")
    parent_commit = relationship("Commit", remote_side=[commit_id], foreign_keys=[parent_commit_id])
    objects = relationship("BlenderObject", back_populates="commit", cascade="all, delete-orphan")


class BlenderObject(Base):
    __tablename__ = "blender_objects"

    object_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commit_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=False)
    object_name = Column(String, nullable=False)
    object_type = Column(String, nullable=False)  # MESH, CAMERA, LIGHT, ARMATURE, etc.
    json_data_path = Column(String, nullable=False)  # Path in object storage
    mesh_data_path = Column(String, nullable=True)
    parent_object_id = Column(UUID(as_uuid=True), ForeignKey("blender_objects.object_id"), nullable=True)
    blob_hash = Column(String, nullable=False, index=True)  # For deduplication
    created_at = Column(DateTime, default=_utcnow)

    commit = relationship("Commit", back_populates="objects")


class ObjectLock(Base):
    __tablename__ = "object_locks"

    lock_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    object_name = Column(String, nullable=False)
    locked_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=True)
    locked_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "object_name", "branch_id", name="unique_object_lock"),)

    project = relationship("Project", back_populates="locks")
    locked_by_user = relationship("User", back_populates="locks")


class ProjectMetadata(Base):
    __tablename__ = "project_metadata"

    metadata_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String, nullable=True)  # Store as JSON string
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("project_id", "key", name="unique_project_metadata"),)

    project = relationship("Project", back_populates="project_metadata")


class ProjectMember(Base):
    """
    Junction table for project collaboration.

    Enables many-to-many relationship between users and projects.
    Roles: viewer (read-only), editor (commit/branch), owner (full control).
    """
    __tablename__ = "project_members"

    member_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default=MemberRole.editor.value, nullable=False)  # viewer / editor / owner
    added_at = Column(DateTime, default=_utcnow, nullable=False)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="unique_project_member"),
        Index("ix_project_members_project_user", "project_id", "user_id"),
    )

    # Relationships
    project = relationship("Project", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="project_memberships")
    added_by_user = relationship("User", foreign_keys=[added_by])


class ProjectInvitation(Base):
    """
    Invitation to join a project.

    Flow: owner/editor sends invite → invitee accepts/declines → on accept, ProjectMember created.
    Invitations expire after INVITE_EXPIRY_DAYS (default 7).
    """
    __tablename__ = "project_invitations"

    invitation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    inviter_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    invitee_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)  # resolved from email/username
    invitee_email = Column(String, nullable=False)  # always stored for display
    role = Column(String, default=MemberRole.editor.value, nullable=False)
    status = Column(String, default=InvitationStatus.pending.value, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    responded_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_invitation_project_email_status", "project_id", "invitee_email", "status"),
        Index("ix_invitation_invitee_status", "invitee_id", "status"),
    )

    # Relationships
    project = relationship("Project", back_populates="invitations")
    inviter = relationship("User", foreign_keys=[inviter_id], back_populates="invitations_sent")
    invitee = relationship("User", foreign_keys=[invitee_id], back_populates="invitations_received")
