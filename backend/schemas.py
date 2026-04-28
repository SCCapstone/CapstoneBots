from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from datetime import datetime
from uuid import UUID
from models import MemberRole

USERNAME_MAX_LENGTH = 32
PASSWORD_MAX_LENGTH = 128
PROJECT_NAME_MAX_LENGTH = 100
PROJECT_DESCRIPTION_MAX_LENGTH = 500

# ============== User Schemas ==============
class UserBase(BaseModel):
    username: str = Field(..., max_length=USERNAME_MAX_LENGTH)
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)

class UserResponse(UserBase):
    user_id: UUID
    created_at: datetime
    last_login: Optional[datetime]
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[EmailStr] = None

class DeleteAccountRequest(BaseModel):
    password: str

# ============== Password Reset Schemas ==============
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)

# ============== Email Verification Schemas ==============
class VerifyEmailRequest(BaseModel):
    token: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

# ============== Project Schemas ==============
class ProjectBase(BaseModel):
    name: str = Field(..., max_length=PROJECT_NAME_MAX_LENGTH)
    description: Optional[str] = Field(default=None, max_length=PROJECT_DESCRIPTION_MAX_LENGTH)
    active: bool = True

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=PROJECT_NAME_MAX_LENGTH)
    description: Optional[str] = Field(default=None, max_length=PROJECT_DESCRIPTION_MAX_LENGTH)
    active: Optional[bool] = None

class ProjectResponse(ProjectBase):
    project_id: UUID
    owner_id: UUID
    default_branch: str = "main"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ============== Commit Schemas ==============
class CommitBase(BaseModel):
    commit_message: str

# Create schema for commits not requiring all fields
class CommitCreate(CommitBase):
    pass

class CommitResponse(CommitBase):
    commit_id: UUID
    project_id: UUID
    branch_id: Optional[UUID] = None
    parent_commit_id: Optional[UUID]
    author_id: Optional[UUID]
    commit_hash: str
    committed_at: datetime
    merge_commit: bool
    merge_parent_id: Optional[UUID]
    branch_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# ============== Branch Schemas ==============
class BranchCreate(BaseModel):
    branch_name: Optional[str] = None
    name: Optional[str] = None
    source_commit_id: Optional[UUID] = None  # If None, branches from default branch HEAD
    parent_branch_id: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_name_present(self):
        if not self.branch_name and not self.name:
            raise ValueError("Either 'branch_name' or legacy 'name' must be provided")
        return self

class BranchResponse(BaseModel):
    branch_id: UUID
    project_id: UUID
    branch_name: str
    head_commit_id: Optional[UUID]
    parent_branch_id: Optional[UUID]
    created_at: datetime
    created_by: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)

class BranchUpdate(BaseModel):
    branch_name: Optional[str] = None

class MergeRequest(BaseModel):
    source_branch_id: UUID  # Branch to merge FROM
    commit_message: Optional[str] = None

class MergeConflictDetail(BaseModel):
    object_name: str
    conflict_type: str  # MODIFIED_BOTH, DELETED_LOCALLY, DELETED_REMOTELY
    source_blob_hash: Optional[str] = None
    target_blob_hash: Optional[str] = None

class MergeConflictResponse(BaseModel):
    conflicts: List["MergeConflictDetail"]
    source_branch_id: UUID
    target_branch_id: UUID
    common_ancestor_commit_id: Optional[UUID]

# ============== Blender Object Schemas ==============
class BlenderObjectBase(BaseModel):
    object_name: str
    object_type: str
    json_data_path: str
    mesh_data_path: Optional[str] = None
    parent_object_id: Optional[UUID] = None
    blob_hash: str

class BlenderObjectCreate(BlenderObjectBase):
    pass

class BlenderObjectResponse(BlenderObjectBase):
    object_id: UUID
    commit_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Request model for creating a commit (includes objects)
class CommitCreateRequest(BaseModel):
    # author_id: UUID | Removed to be inferred from auth token
    commit_message: str
    objects: List[BlenderObjectCreate]
    branch_id: Optional[UUID] = None  # If None, uses project's default branch
    merge_commit: bool = False
    merge_parent_id: Optional[UUID] = None

# ============== Object Lock Schemas ==============
class ObjectLockBase(BaseModel):
    object_name: str

class ObjectLockCreate(ObjectLockBase):
    expires_at: datetime
    branch_id: Optional[UUID] = None  # If None, uses project's default branch
    # locked_by: UUID | Removed to be inferred from auth token

class ObjectLockResponse(ObjectLockBase):
    lock_id: UUID
    project_id: UUID
    locked_by: UUID
    branch_id: Optional[UUID] = None
    locked_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ============== (Merge Conflict DB schemas removed — conflicts are now returned inline by the merge endpoint) ==============

# ============== Project Metadata Schemas ==============
class ProjectMetadataBase(BaseModel):
    key: str
    value: Optional[str] = None

class ProjectMetadataResponse(ProjectMetadataBase):
    metadata_id: UUID
    project_id: UUID
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============== Storage & Versioning Schemas ==============
class StorageObjectInfo(BaseModel):
    """Information about a stored object in MinIO"""
    name: str
    size: int
    etag: str
    last_modified: datetime
    version_id: Optional[str] = None


class ProjectStorageStats(BaseModel):
    """Storage statistics for a project"""
    project_id: UUID
    total_bytes: int
    objects_bytes: int
    versions_bytes: int
    total_mb: float


class CommitSnapshotResponse(BaseModel):
    """Response for commit snapshot operations"""
    commit_id: UUID
    snapshot_path: str
    snapshot_size: int
    created_at: datetime


class ObjectDownloadResponse(BaseModel):
    """Response containing object data for download"""
    object_id: UUID
    object_name: str
    object_type: str
    json_data: Dict[str, Any]
    mesh_data: Optional[bytes] = None
    storage_info: Optional[StorageObjectInfo] = None


class CommitDataRequest(BaseModel):
    """Enhanced commit request with optional mesh data"""
    author_id: UUID
    commit_message: str
    objects: List[BlenderObjectCreate]
    include_snapshot: bool = False  # Whether to save full .blend snapshot


class VersionHistoryResponse(BaseModel):
    """Response for version history listing"""
    commit_id: UUID
    commit_hash: str
    commit_message: str
    author_id: Optional[UUID] = None
    committed_at: datetime
    snapshot_path: Optional[str]
    snapshot_size: Optional[int]


# ============== Project Collaboration Schemas ==============

class ProjectMemberAdd(BaseModel):
    """
    Schema for sending a project invitation.

    Accepts email or username to identify the user, plus a role.
    """
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    role: MemberRole = MemberRole.editor

class ProjectMemberResponse(BaseModel):
    """Response containing project member information"""
    member_id: UUID
    project_id: UUID
    user_id: UUID
    username: str
    email: EmailStr
    role: str
    added_at: datetime
    added_by: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)

class ProjectMemberRemove(BaseModel):
    """Schema for removing a member from a project"""
    user_id: UUID

class MemberRoleUpdate(BaseModel):
    """Schema for changing a member's role"""
    role: MemberRole

class InvitationCreate(ProjectMemberAdd):
    """
    Schema for creating a project invitation.
    Provide either email or username (at least one required).
    Inherits from ProjectMemberAdd — identical fields, separate type for clarity.
    """
    pass

class InvitationResponse(BaseModel):
    """Response containing invitation details"""
    invitation_id: UUID
    project_id: UUID
    project_name: Optional[str] = None
    inviter_id: UUID
    inviter_username: Optional[str] = None
    invitee_id: Optional[UUID]
    invitee_email: EmailStr
    invitee_username: Optional[str] = None
    role: str
    status: str
    created_at: datetime
    expires_at: datetime
    responded_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

class ProjectWithMembersResponse(ProjectResponse):
    """Extended project response that includes member list"""
    members: List[ProjectMemberResponse]
    is_owner: bool
    current_user_role: Optional[str]

    model_config = ConfigDict(from_attributes=True)


