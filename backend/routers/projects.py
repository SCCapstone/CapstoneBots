"""
Project Management Routes

This module handles all project-related endpoints for the CapstoneBots API.
It provides Git-like version control functionality for Blender projects, including:
- Project CRUD operations
- Branch management
- Commit history and creation
- Object locking (preventing concurrent edits)
- Merge conflict tracking

The API mimics Git workflows adapted for 3D asset collaboration.
"""

from typing import List
from uuid import UUID
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, text as sa_text
from sqlalchemy.orm import joinedload

from database import get_db
from models import (
    Project, Branch, Commit, BlenderObject, ObjectLock,
    User, ProjectMember, ProjectInvitation,
    MemberRole, InvitationStatus, INVITE_EXPIRY_DAYS, role_at_least,
)
from schemas import (
    ProjectCreate, ProjectResponse, ProjectUpdate, ProjectBase,
    BranchCreate, BranchResponse,
    CommitCreate, CommitResponse, CommitCreateRequest,
    BlenderObjectCreate, BlenderObjectResponse,
    ObjectLockCreate, ObjectLockResponse,
    ProjectMemberAdd, ProjectMemberResponse, ProjectMemberRemove, ProjectWithMembersResponse,
    InvitationCreate, InvitationResponse, MemberRoleUpdate,
)
from utils.auth import get_current_user
from utils.permissions import check_project_access, is_project_member, get_user_projects
from utils.project_utils import delete_project_data

# Initialize the router for project-related endpoints
router = APIRouter()

# ============== Project Routes ==============

@router.get("", response_model=List[ProjectResponse])
async def get_projects(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Get all projects accessible by the authenticated user.
    
    This endpoint retrieves all Blender projects that the user can access:
    - Projects owned by the user
    - Projects where the user is a member (added by another user)
    
    This is the primary endpoint used by the Blender add-on to show available projects.
    When users log into the add-on, this endpoint returns all their accessible projects.
    
    Args:
        db: Database session dependency
        current_user: Authenticated user from JWT token
        
    Returns:
        List[ProjectResponse]: List of accessible projects with metadata
        
    Example:
        GET /api/projects
        Headers: Authorization: Bearer <token>
        
        Response:
        [
            {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "My Blender Project",
                "description": "A collaborative 3D scene",
                "owner_id": "user-id",
                "created_at": "2025-12-01T10:00:00"
            },
            {
                "project_id": "987e6543-e21b-12d3-a456-426614174999",
                "name": "Team Project",
                "description": "Shared project I was added to",
                "owner_id": "other-user-id",
                "created_at": "2025-11-15T14:30:00"
            }
        ]
    """
    # Use the helper function to get all projects user has access to
    projects = await get_user_projects(current_user.user_id, db)
    
    # Sort by most recently updated
    projects.sort(key=lambda p: p.updated_at, reverse=True)
    
    return projects

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
        project: ProjectCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Create a new Blender project with version control.
    
    This endpoint creates a new project and automatically initializes it with a
    'main' branch (similar to Git's default branch). The authenticated user becomes
    the project owner.
    
    Args:
        project: ProjectCreate schema with name, description, and active status
        db: Database session dependency
        current_user: Authenticated user from JWT token (becomes owner)
        
    Returns:
        ProjectResponse: Created project details with generated ID
        
    Example:
        POST /api/projects
        Headers: Authorization: Bearer <token>
        {
            "name": "Space Station Scene",
            "description": "Collaborative sci-fi environment",
            "active": true
        }
    """
    # Create new project instance with current user as owner
    new_project = Project(
        name=project.name,
        description=project.description,
        active=project.active,
        owner_id=current_user.user_id,
    )
    db.add(new_project)
    await db.flush()  # Flush to get the project_id without committing yet

    # Automatically create a default 'main' branch (like Git init)
    # This is the starting point for all commits in the project
    main_branch = Branch(
        project_id=new_project.project_id,
        branch_name="main",
        created_by=new_project.owner_id,
    )
    db.add(main_branch)
    
    # Add the owner as a project member with "owner" role
    # This ensures the owner appears in the members list and collaboration system works consistently
    owner_member = ProjectMember(
        project_id=new_project.project_id,
        user_id=current_user.user_id,
        role="owner",
        added_by=current_user.user_id
    )
    db.add(owner_member)
    
    await db.commit()  # Commit project, branch, and membership together
    await db.refresh(new_project)  # Refresh to get all generated fields
    return new_project

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed information about a specific project (members only)."""
    project, _ = await check_project_access(project_id, current_user.user_id, db)
    return project

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    update_data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update project details (name, description, or active status). Owner only."""
    project, _ = await check_project_access(project_id, current_user.user_id, db, require_owner=True)

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(project, key, value)

    await db.commit()
    await db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete a project and all associated data. Owner only."""
    await check_project_access(project_id, current_user.user_id, db, require_owner=True)
    await delete_project_data(db, project_id)
    await db.commit()

# ============== Branch Routes ==============

@router.get("/{project_id}/branches", response_model=List[BranchResponse])
async def get_project_branches(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all branches in a project (members only)."""
    await check_project_access(project_id, current_user.user_id, db)
    query = (
        select(Branch)
        .where(Branch.project_id == project_id)
        .order_by(Branch.created_at)
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/{project_id}/branches", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    project_id: UUID,
    req: BranchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new branch in a project (similar to 'git branch <name>').
    
    This endpoint creates a new branch for parallel development. Branches are used
    when team members want to work on features independently without affecting the
    main branch. Each branch can have its own series of commits.
    
    Args:
        project_id: UUID of the parent project
        branch: BranchCreate schema containing branch name and creator info
        db: Database session dependency
        
    Returns:
        BranchResponse: Created branch details
        
    Raises:
        HTTPException 404: If parent project doesn't exist
        
    Example:
        POST /api/projects/123e4567-e89b-12d3-a456-426614174000/branches
        {
            "branch_name": "feature-lighting",
            "created_by": "user-id"
        }
    """
    # Validate branch name
    branch_name = req.name.strip() if req.name else ""
    if not branch_name:
        raise HTTPException(status_code=400, detail="Branch name cannot be empty")
    if len(branch_name) > 255:
        raise HTTPException(status_code=400, detail="Branch name too long (max 255 characters)")
    if "/" in branch_name:
        raise HTTPException(status_code=400, detail="Branch name cannot contain slashes")

    # Editors and above can create branches
    await check_project_access(project_id, current_user.user_id, db, require_role=MemberRole.editor)

    # Create new branch within the project
    new_branch = Branch(
        project_id=project_id,
        branch_name=branch_name,
        parent_branch_id=req.parent_branch_id,
        created_by=current_user.user_id,
    )
    db.add(new_branch)
    await db.commit()
    await db.refresh(new_branch)

    return new_branch

# ============== Commit Routes ==============

@router.get("/{project_id}/commits", response_model=List[CommitResponse])
async def get_commit_history(
        project_id: UUID,
        branch_name: str = "main",
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Get commit history for a branch (members only)."""
    await check_project_access(project_id, current_user.user_id, db)

    # 2) Find the branch for this project + name
    branch_result = await db.execute(
        select(Branch).where(
            Branch.project_id == project_id,
            Branch.branch_name == branch_name,
            )
    )
    branch = branch_result.scalar_one_or_none()
    if branch is None:
        # No such branch -> no commits
        return []

    # 3) Get commits for that branch, newest first
    commits_result = await db.execute(
        select(Commit)
        .where(
            Commit.project_id == project_id,
            Commit.branch_id == branch.branch_id,
            )
        .options(joinedload(Commit.author))  # keep eager-loaded author
        .order_by(Commit.committed_at.desc())
    )

    commits = commits_result.scalars().unique().all()
    return commits

@router.post("/{project_id}/commits", response_model=CommitResponse, status_code=status.HTTP_201_CREATED)
async def create_commit(
    project_id: UUID,
    data: CommitCreateRequest,  # <- use the request model with branch_id, commit_message, objects
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new commit with Blender objects (similar to 'git commit').
    
    This endpoint records a snapshot of changes to Blender objects. Each commit
    contains:
    - A unique hash (for integrity verification)
    - Reference to parent commit (building a history chain)
    - List of modified Blender objects with their data
    - Commit message describing the changes
    
    The commit becomes the new HEAD of the branch, moving the branch pointer forward.
    
    Args:
        project_id: UUID of the project
        data: CommitCreateRequest with branch_id, message, and objects
        db: Database session dependency
        
    Returns:
        CommitResponse: Created commit details with generated hash
        
    Raises:
        HTTPException 404: If branch doesn't exist
        HTTPException 423: If any object being committed is locked by another user
    """

    # Editors and above can commit
    await check_project_access(project_id, current_user.user_id, db, require_role=MemberRole.editor)

    if not data.objects:
        raise HTTPException(status_code=400, detail="Commit must include at least one object")

    # Verify the branch exists and belongs to this project
    branch = await db.get(Branch, data.branch_id)
    if not branch or branch.project_id != project_id:
        raise HTTPException(status_code=404, detail="Branch not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Enforce object locks
    for obj_data in data.objects:
        obj_name = obj_data.object_name
        lock_query = (
            select(ObjectLock)
            .where(
                ObjectLock.project_id == project_id,
                ObjectLock.object_name == obj_name,
                ObjectLock.branch_id == data.branch_id,
            )
        )
        lock_result = await db.execute(lock_query)
        lock = lock_result.scalar_one_or_none()

        if lock and lock.expires_at:
            expires = lock.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                await db.delete(lock)
                await db.flush()
                lock = None

        if lock and lock.locked_by != current_user.user_id:
            raise HTTPException(
                status_code=423,
                detail=f"Object '{obj_name}' is locked by another user.",
            )

    # Generate unique commit hash using SHA256
    commit_content = (
        f"{project_id}{data.branch_id}{current_user.user_id}"
        f"{data.commit_message}{now.isoformat()}"
    )
    commit_hash = hashlib.sha256(commit_content.encode()).hexdigest()

    # Create the commit record
    new_commit = Commit(
        project_id=project_id,
        branch_id=data.branch_id,
        parent_commit_id=branch.head_commit_id,
        author_id=current_user.user_id,
        commit_message=data.commit_message,
        commit_hash=commit_hash,
        committed_at=now,
    )
    db.add(new_commit)
    await db.flush()

    # Add all Blender objects that are part of this commit
    for obj_data in data.objects:
        blender_obj = BlenderObject(
            commit_id=new_commit.commit_id,
            **obj_data.model_dump()
        )
        db.add(blender_obj)
    
    # Update the branch HEAD pointer to this new commit
    branch.head_commit_id = new_commit.commit_id
    
    await db.commit()
    await db.refresh(new_commit)
    return new_commit

@router.get("/{project_id}/commits/{commit_id}/objects", response_model=List[BlenderObjectResponse])
async def get_commit_objects(
    project_id: UUID,
    commit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all Blender objects in a specific commit (members only)."""
    await check_project_access(project_id, current_user.user_id, db)
    query = (
        select(BlenderObject)
        .where(BlenderObject.commit_id == commit_id)
        .order_by(BlenderObject.object_name)
    )
    result = await db.execute(query)
    return result.scalars().all()

# ============== Object Lock Routes ==============

@router.get("/{project_id}/locks", response_model=List[ObjectLockResponse])
async def get_object_locks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all active object locks in a project (members only)."""
    await check_project_access(project_id, current_user.user_id, db)
    query = (
        select(ObjectLock)
        .where(ObjectLock.project_id == project_id)
        .order_by(ObjectLock.locked_at)
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/{project_id}/locks", response_model=ObjectLockResponse, status_code=status.HTTP_201_CREATED)
async def lock_object(
    project_id: UUID,
    lock_data: ObjectLockCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lock a Blender object to prevent concurrent edits.
    
    This endpoint creates an exclusive lock on a specific object within a branch.
    Only the user who holds the lock can edit the object. This prevents merge
    conflicts and ensures data integrity in collaborative environments.
    
    Locks are time-limited (expires_at) to prevent indefinite locks if a user
    disconnects or forgets to release the lock.
    
    Args:
        project_id: UUID of the project
        lock_data: ObjectLockCreate with object_name, branch_id, expires_at
        db: Database session dependency
        
    Returns:
        ObjectLockResponse: Created lock details
        
    Raises:
        HTTPException 409: If object is already locked by another user
        
    Example:
        POST /api/projects/123e4567-e89b-12d3-a456-426614174000/locks
        {
            "object_name": "Cube",
            "branch_id": "branch-uuid",
            "expires_at": "2025-12-02T16:00:00"
        }
    """
    # Editors and above can acquire locks
    await check_project_access(project_id, current_user.user_id, db, require_role=MemberRole.editor)

    # Check if the object is already locked in this branch
    existing_lock = (
        select(ObjectLock)
        .where(
            ObjectLock.project_id == project_id,
            ObjectLock.object_name == lock_data.object_name,
            ObjectLock.branch_id == lock_data.branch_id,
        )
    )
    result = await db.execute(existing_lock)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Object is already locked")

    # Create the lock record
    new_lock = ObjectLock(
        project_id=project_id,
        object_name=lock_data.object_name,
        locked_by=current_user.user_id,  # Infer from auth token
        branch_id=lock_data.branch_id,
        expires_at=lock_data.expires_at,
    )
    db.add(new_lock)
    await db.commit()
    await db.refresh(new_lock)
    return new_lock

@router.delete("/{project_id}/locks/{lock_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_object(
    project_id: UUID,
    lock_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Release a lock. Only the lock holder or a project owner can release a lock."""
    lock = await db.get(ObjectLock, lock_id)
    if not lock or lock.project_id != project_id:
        raise HTTPException(status_code=404, detail="Lock not found")

    _, caller_role = await check_project_access(project_id, current_user.user_id, db)
    if lock.locked_by != current_user.user_id and caller_role != MemberRole.owner.value:
        raise HTTPException(
            status_code=403,
            detail="Only the lock holder or project owner can release this lock",
        )

    await db.delete(lock)
    await db.commit()


# ============== Project Collaboration Routes ==============

# ---------- helper ----------
def _build_invitation_response(inv: ProjectInvitation, project: Project, inviter: User, invitee: User = None) -> InvitationResponse:
    return InvitationResponse(
        invitation_id=inv.invitation_id,
        project_id=inv.project_id,
        project_name=project.name,
        inviter_id=inv.inviter_id,
        inviter_username=inviter.username,
        invitee_id=inv.invitee_id,
        invitee_email=inv.invitee_email,
        invitee_username=invitee.username if invitee else None,
        role=inv.role,
        status=inv.status,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        responded_at=inv.responded_at,
    )


@router.post("/{project_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def send_invitation(
    project_id: UUID,
    data: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a project invitation to a user by email or username.
    
    Only owners and editors can send invitations.
    Invitations expire after INVITE_EXPIRY_DAYS (default 7).
    """
    # Validate role value
    if data.role not in [r.value for r in MemberRole]:
        raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}. Must be viewer, editor, or owner.")

    # Check caller has at least editor access
    project, caller_role = await check_project_access(
        project_id, current_user.user_id, db, require_role=MemberRole.editor
    )

    # Only owners can invite with "owner" role
    if data.role == MemberRole.owner.value and caller_role != MemberRole.owner.value:
        raise HTTPException(status_code=403, detail="Only project owners can assign the owner role.")

    # Resolve the invitee
    if not data.email and not data.username:
        raise HTTPException(status_code=400, detail="Provide either email or username.")

    if data.email:
        result = await db.execute(select(User).where(User.email == data.email))
    else:
        result = await db.execute(select(User).where(User.username == data.username))
    invitee = result.scalars().first()

    if not invitee:
        raise HTTPException(status_code=404, detail="No user found with that email or username.")

    invitee_email = invitee.email

    # Can't invite yourself
    if invitee.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="You cannot invite yourself.")

    # Check if already a member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == invitee.user_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="User is already a member of this project.")

    # Check for existing pending invitation
    existing_inv = await db.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.project_id == project_id,
            ProjectInvitation.invitee_email == invitee_email,
            ProjectInvitation.status == InvitationStatus.pending.value,
        )
    )
    if existing_inv.scalars().first():
        raise HTTPException(status_code=409, detail="A pending invitation already exists for this user.")

    # Create invitation
    invitation = ProjectInvitation(
        project_id=project_id,
        inviter_id=current_user.user_id,
        invitee_id=invitee.user_id,
        invitee_email=invitee_email,
        role=data.role,
        status=InvitationStatus.pending.value,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    return _build_invitation_response(invitation, project, current_user, invitee)


@router.get("/{project_id}/invitations", response_model=List[InvitationResponse])
async def get_project_invitations(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all invitations for a project (owners and editors)."""
    project, _ = await check_project_access(
        project_id, current_user.user_id, db, require_role=MemberRole.editor
    )

    result = await db.execute(
        select(ProjectInvitation, User)
        .outerjoin(User, ProjectInvitation.invitee_id == User.user_id)
        .where(ProjectInvitation.project_id == project_id)
        .order_by(ProjectInvitation.created_at.desc())
    )
    rows = result.all()

    # We need inviter info too
    inviter_ids = {inv.inviter_id for inv, _ in rows}
    inviter_result = await db.execute(select(User).where(User.user_id.in_(inviter_ids)))
    inviters = {u.user_id: u for u in inviter_result.scalars().all()}

    response = []
    for inv, invitee in rows:
        inviter = inviters.get(inv.inviter_id)
        response.append(_build_invitation_response(inv, project, inviter, invitee))
    return response


@router.delete("/{project_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    project_id: UUID,
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending invitation. Only the inviter or project owner can cancel."""
    project, caller_role = await check_project_access(
        project_id, current_user.user_id, db, require_role=MemberRole.editor
    )

    invitation = await db.get(ProjectInvitation, invitation_id)
    if not invitation or invitation.project_id != project_id:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invitation.status != InvitationStatus.pending.value:
        raise HTTPException(status_code=400, detail="Only pending invitations can be cancelled.")

    # Only inviter or owner can cancel
    if invitation.inviter_id != current_user.user_id and caller_role != MemberRole.owner.value:
        raise HTTPException(status_code=403, detail="Only the inviter or project owner can cancel this invitation.")

    await db.delete(invitation)
    await db.commit()


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: UUID,
    member_data: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add a user to a project by email or username (creates an invitation).
    
    This endpoint maintains backward compatibility: it sends an invitation
    that the invitee must accept. For immediate access, use the invitation
    accept endpoint.
    """
    # Validate role
    role = member_data.role or MemberRole.editor.value
    if role not in [r.value for r in MemberRole]:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    project, caller_role = await check_project_access(
        project_id, current_user.user_id, db, require_role=MemberRole.editor
    )

    # Only project owners may assign the owner role when inviting members
    if role == MemberRole.owner.value and caller_role != MemberRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project owners can assign the owner role.",
        )
    # Resolve user
    if not member_data.email and not member_data.username:
        raise HTTPException(status_code=400, detail="Provide either email or username.")

    if member_data.email:
        result = await db.execute(select(User).where(User.email == member_data.email))
    else:
        result = await db.execute(select(User).where(User.username == member_data.username))
    user_to_add = result.scalars().first()

    if not user_to_add:
        raise HTTPException(status_code=404, detail="No user found with that email or username.")

    # Prevent self-invitation
    if user_to_add.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="You cannot invite yourself to a project.")
    # Check already member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_to_add.user_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="User is already a member of this project.")

    # Check for pending invite
    existing_inv = await db.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.project_id == project_id,
            ProjectInvitation.invitee_email == user_to_add.email,
            ProjectInvitation.status == InvitationStatus.pending.value,
        )
    )
    if existing_inv.scalars().first():
        raise HTTPException(status_code=409, detail="A pending invitation already exists for this user.")

    # Create invitation
    invitation = ProjectInvitation(
        project_id=project_id,
        inviter_id=current_user.user_id,
        invitee_id=user_to_add.user_id,
        invitee_email=user_to_add.email,
        role=role,
        status=InvitationStatus.pending.value,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Return a ProjectMemberResponse-shaped object so frontend compatibility is kept
    return ProjectMemberResponse(
        member_id=invitation.invitation_id,  # use invitation_id as member_id for compat
        project_id=invitation.project_id,
        user_id=user_to_add.user_id,
        username=user_to_add.username,
        email=user_to_add.email,
        role=invitation.role,
        added_at=invitation.created_at,
        added_by=current_user.user_id,
    )


@router.get("/{project_id}/members", response_model=List[ProjectMemberResponse])
async def get_project_members(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all members of a project."""
    project, _ = await check_project_access(project_id, current_user.user_id, db)

    query = (
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.added_at.asc())
    )
    result = await db.execute(query)
    members_with_users = result.all()

    response = []
    for member, user in members_with_users:
        response.append(ProjectMemberResponse(
            member_id=member.member_id,
            project_id=member.project_id,
            user_id=member.user_id,
            username=user.username,
            email=user.email,
            role=member.role,
            added_at=member.added_at,
            added_by=member.added_by,
        ))

    return response


@router.put("/{project_id}/members/{member_id}/role", response_model=ProjectMemberResponse)
async def update_member_role(
    project_id: UUID,
    member_id: UUID,
    data: MemberRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change a member's role. Only the project owner can change roles."""
    if data.role not in [r.value for r in MemberRole]:
        raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}")

    project, _ = await check_project_access(
        project_id, current_user.user_id, db, require_owner=True
    )

    member = await db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Member not found in this project.")

    # Can't change own role
    if member.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role.")

    member.role = data.role
    await db.commit()
    await db.refresh(member)

    # Fetch user info for response
    user = await db.get(User, member.user_id)
    return ProjectMemberResponse(
        member_id=member.member_id,
        project_id=member.project_id,
        user_id=member.user_id,
        username=user.username,
        email=user.email,
        role=member.role,
        added_at=member.added_at,
        added_by=member.added_by,
    )


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from a project. Only the project owner can remove members."""
    project, _ = await check_project_access(
        project_id, current_user.user_id, db, require_owner=True
    )

    member = await db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Member not found in this project.")

    if member.role == MemberRole.owner.value:
        raise HTTPException(
            status_code=409,
            detail="Cannot remove the project owner. Transfer ownership first or delete the project."
        )

    await db.delete(member)
    await db.commit()
    return None

