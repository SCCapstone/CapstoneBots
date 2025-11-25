from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, LargeBinary, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid
from datetime import datetime
import enum

class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    projects = relationship("Project", back_populates="owner")
    commits = relationship("Commit", back_populates="author")
    locks = relationship("ObjectLock", back_populates="locked_by_user")


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    default_branch = Column(String, default="main")
    active = Column(Boolean, default=True)

    owner = relationship("User", back_populates="projects")
    branches = relationship("Branch", back_populates="project", cascade="all, delete-orphan")
    commits = relationship("Commit", back_populates="project", cascade="all, delete-orphan")
    locks = relationship("ObjectLock", back_populates="project", cascade="all, delete-orphan")
    conflicts = relationship("MergeConflict", back_populates="project", cascade="all, delete-orphan")
    project_metadata = relationship("ProjectMetadata", back_populates="project", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"

    branch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    branch_name = Column(String, nullable=False)
    head_commit_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=True)
    parent_branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "branch_name", name="unique_project_branch"),)

    project = relationship("Project", back_populates="branches")
    head_commit = relationship("Commit", foreign_keys=[head_commit_id])
    parent_branch = relationship("Branch", remote_side=[branch_id])
    commits = relationship("Commit", back_populates="branch", foreign_keys="Commit.branch_id")


class Commit(Base):
    __tablename__ = "commits"

    commit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=False)
    parent_commit_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    commit_message = Column(Text, nullable=False)
    commit_hash = Column(String, unique=True, nullable=False, index=True)
    committed_at = Column(DateTime, default=datetime.utcnow)
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
    created_at = Column(DateTime, default=datetime.utcnow)

    commit = relationship("Commit", back_populates="objects")


class ObjectLock(Base):
    __tablename__ = "object_locks"

    lock_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    object_name = Column(String, nullable=False)
    locked_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=False)
    locked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "object_name", "branch_id", name="unique_object_lock"),)

    project = relationship("Project", back_populates="locks")
    locked_by_user = relationship("User", back_populates="locks")


class MergeConflict(Base):
    __tablename__ = "merge_conflicts"

    conflict_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    source_commit_id = Column(UUID(as_uuid=True), ForeignKey("commits.commit_id"), nullable=False)
    target_branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.branch_id"), nullable=False)
    object_name = Column(String, nullable=False)
    conflict_type = Column(String, nullable=False)  # MODIFY_MODIFY, DELETE_MODIFY, etc.
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="conflicts")


class ProjectMetadata(Base):
    __tablename__ = "project_metadata"

    metadata_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String, nullable=True)  # Store as JSON string
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("project_id", "key", name="unique_project_metadata"),)

    project = relationship("Project", back_populates="project_metadata")
