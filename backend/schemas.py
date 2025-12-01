from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime
from uuid import UUID

# ============== User Schemas ==============
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    user_id: UUID
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[EmailStr] = None

# ============== Project Schemas ==============
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    active: bool = True

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

class ProjectResponse(ProjectBase):
    project_id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    default_branch: str

    class Config:
        from_attributes = True

# ============== Branch Schemas ==============
class BranchBase(BaseModel):
    branch_name: str
    parent_branch_id: Optional[UUID] = None

class BranchCreate(BranchBase):
    created_by: UUID

class BranchResponse(BranchBase):
    branch_id: UUID
    project_id: UUID
    head_commit_id: Optional[UUID]
    created_at: datetime
    created_by: UUID

    class Config:
        from_attributes = True

# ============== Commit Schemas ==============
class CommitBase(BaseModel):
    commit_message: str

class CommitCreate(CommitBase):
    pass

class CommitResponse(CommitBase):
    commit_id: UUID
    project_id: UUID
    branch_id: UUID
    parent_commit_id: Optional[UUID]
    author_id: UUID
    commit_hash: str
    committed_at: datetime
    merge_commit: bool
    merge_parent_id: Optional[UUID]

    class Config:
        from_attributes = True

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

    class Config:
        from_attributes = True

# Request model for creating a commit (includes objects)
class CommitCreateRequest(BaseModel):
    branch_id: UUID
    author_id: UUID
    commit_message: str
    objects: List[BlenderObjectCreate]

# ============== Object Lock Schemas ==============
class ObjectLockBase(BaseModel):
    object_name: str

class ObjectLockCreate(ObjectLockBase):
    expires_at: datetime
    branch_id: UUID
    locked_by: UUID

class ObjectLockResponse(ObjectLockBase):
    lock_id: UUID
    project_id: UUID
    locked_by: UUID
    branch_id: UUID
    locked_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True

# ============== Merge Conflict Schemas ==============
class MergeConflictBase(BaseModel):
    object_name: str
    conflict_type: str

class MergeConflictResponse(MergeConflictBase):
    conflict_id: UUID
    project_id: UUID
    source_commit_id: UUID
    target_branch_id: UUID
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Project Metadata Schemas ==============
class ProjectMetadataBase(BaseModel):
    key: str
    value: Optional[str] = None

class ProjectMetadataResponse(ProjectMetadataBase):
    metadata_id: UUID
    project_id: UUID
    updated_at: datetime

    class Config:
        from_attributes = True
