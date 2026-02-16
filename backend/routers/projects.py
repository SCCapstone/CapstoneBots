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
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import get_db
from models import Project, Branch, Commit, BlenderObject, ObjectLock, MergeConflict, User, ProjectMember
from schemas import (
    ProjectCreate, ProjectResponse, ProjectUpdate, ProjectBase,
    BranchCreate, BranchResponse,
    CommitCreate, CommitResponse, CommitCreateRequest,
    BlenderObjectCreate, BlenderObjectResponse,
    ObjectLockCreate, ObjectLockResponse,
    MergeConflictResponse,
    ProjectMemberAdd, ProjectMemberResponse, ProjectMemberRemove, ProjectWithMembersResponse,
)
from utils.auth import get_current_user
from utils.permissions import check_project_access, is_project_member, get_user_projects

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
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific project.
    
    This endpoint retrieves a single project by its unique ID. Used to display
    project details, settings, and metadata.
    
    Args:
        project_id: UUID of the project to retrieve
        db: Database session dependency
        
    Returns:
        ProjectResponse: Project details and metadata
        
    Raises:
        HTTPException 404: If project with given ID doesn't exist
        
    Example:
        GET /api/projects/123e4567-e89b-12d3-a456-426614174000
    """
    # Fetch project by primary key (UUID)
    result = await db.get(Project, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    update_data: ProjectUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update project details (name, description, or active status).
    
    This endpoint allows partial updates - only fields provided in the request
    will be modified. Used for renaming projects, updating descriptions, or
    archiving/activating projects.
    
    Args:
        project_id: UUID of the project to update
        update_data: ProjectUpdate schema with fields to modify
        db: Database session dependency
        
    Returns:
        ProjectResponse: Updated project details
        
    Raises:
        HTTPException 404: If project doesn't exist
        
    Example:
        PUT /api/projects/123e4567-e89b-12d3-a456-426614174000
        {
            "name": "Updated Project Name",
            "active": false
        }
    """
    # Fetch the project to update
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Only update fields that were provided (exclude_unset=True)
    # This allows partial updates without overwriting other fields
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(project, key, value)
    
    await db.commit()
    await db.refresh(project)  # Get the updated state from DB
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Permanently delete a project and all associated data.
    
    WARNING: This is a destructive operation that will cascade delete all related
    data including branches, commits, objects, locks, and conflicts. This action
    cannot be undone.
    
    Args:
        project_id: UUID of the project to delete
        db: Database session dependency
        
    Returns:
        No content (204 status code)
        
    Raises:
        HTTPException 404: If project doesn't exist
        
    Example:
        DELETE /api/projects/123e4567-e89b-12d3-a456-426614174000
    """
    # Fetch the project to delete
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete the project (cascade will remove all related records)
    await db.delete(project)
    await db.commit()

# ============== Branch Routes ==============

@router.get("/{project_id}/branches", response_model=List[BranchResponse])
async def get_project_branches(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all branches in a project (similar to 'git branch').
    
    This endpoint lists all branches within a project. Branches allow multiple
    team members to work on different features simultaneously without conflicts.
    Similar to Git branches, each branch maintains its own commit history.
    
    Args:
        project_id: UUID of the project
        db: Database session dependency
        
    Returns:
        List[BranchResponse]: All branches ordered by creation date
        
    Example:
        GET /api/projects/123e4567-e89b-12d3-a456-426614174000/branches
        
        Response:
        [
            {
                "branch_id": "uuid",
                "branch_name": "main",
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "created_by": "user-id",
                "created_at": "2025-12-01T10:00:00"
            }
        ]
    """
    # Query all branches for this project, sorted by creation time
    query = (
        select(Branch)
        .where(Branch.project_id == project_id)
        .order_by(Branch.created_at)  # Oldest first (main branch typically first)
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
    # Verify the project exists before creating a branch
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    
    # Create new branch within the project
    new_branch = Branch(
        project_id=project_id,
        branch_name=req.name,                 # map name -> branch_name
        parent_branch_id=req.parent_branch_id,
        created_by=current_user.user_id,      # use auth user, NOT request body
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
):
    """
    Get commit history for a branch (similar to 'git log').

    Returns an empty list if the branch has no commits or does not exist.
    """

    # 1) Ensure the project exists (optional but nice for clarity)
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    # Verify the branch exists
    branch = await db.get(Branch, data.branch_id)
    if not branch or branch.project_id != project_id:
        raise HTTPException(status_code=404, detail="Branch not found")

    # ============================
    # Enforce object locks (Issue #33)
    # ============================
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

        if lock and lock.expires_at and lock.expires_at < datetime.utcnow():
            await db.delete(lock)
            await db.commit()
            lock = None

        if lock and lock.locked_by != current_user.user_id:
            raise HTTPException(
                status_code=423,
                detail=f"Object '{obj_name}' is locked by another user.",
            )
    
    # Generate unique commit hash using SHA256
    now = datetime.utcnow()
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
            **obj_data.dict()
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
    db: AsyncSession = Depends(get_db)
):
    """
    Get all Blender objects in a specific commit (similar to 'git show').
    
    This endpoint retrieves the list of 3D objects that were modified or included
    in a specific commit. Each object contains file paths to the asset data stored
    in object storage (MinIO/S3), along with metadata about the object type and
    transformations.
    
    Args:
        project_id: UUID of the project (for context/validation)
        commit_id: UUID of the commit to inspect
        db: Database session dependency
        
    Returns:
        List[BlenderObjectResponse]: All objects in the commit, sorted by name
        
    Example:
        GET /api/projects/123e4567-e89b-12d3-a456-426614174000/commits/commit-uuid/objects
        
        Response:
        [
            {
                "object_id": "uuid",
                "object_name": "Cube",
                "object_type": "MESH",
                "file_path": "s3://bucket/project/cube.blend",
                "commit_id": "commit-uuid"
            }
        ]
    """
    # Query all Blender objects associated with this commit
    query = (
        select(BlenderObject)
        .where(BlenderObject.commit_id == commit_id)
        .order_by(BlenderObject.object_name)  # Alphabetical order for consistency
    )
    result = await db.execute(query)
    return result.scalars().all()

# ============== Object Lock Routes ==============

@router.get("/{project_id}/locks", response_model=List[ObjectLockResponse])
async def get_object_locks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all active object locks in a project.
    
    This endpoint retrieves all currently locked 3D objects. Locks prevent
    multiple users from editing the same object simultaneously, avoiding merge
    conflicts. Similar to file locking in Git LFS.
    
    Before editing an object, clients should:
    1. Check if the object is locked
    2. Acquire a lock if available
    3. Edit the object
    4. Commit changes
    5. Release the lock
    
    Args:
        project_id: UUID of the project
        db: Database session dependency
        
    Returns:
        List[ObjectLockResponse]: All active locks, ordered by lock time
        
    Example:
        GET /api/projects/123e4567-e89b-12d3-a456-426614174000/locks
        
        Response:
        [
            {
                "lock_id": "uuid",
                "object_name": "Cube",
                "locked_by": "user-id",
                "locked_at": "2025-12-02T14:00:00",
                "expires_at": "2025-12-02T16:00:00"
            }
        ]
    """
    # Query all active locks for this project
    query = (
        select(ObjectLock)
        .where(ObjectLock.project_id == project_id)
        .order_by(ObjectLock.locked_at)  # Oldest locks first
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
    # Check if the object is already locked in this branch
    # Prevents multiple users from locking the same object simultaneously
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
    db: AsyncSession = Depends(get_db)
):
    """
    Release a lock on an object, allowing others to edit it.
    
    This endpoint removes an object lock, typically called after a user finishes
    editing and commits their changes. Once unlocked, other team members can
    acquire the lock and make their own edits.
    
    Best practice: Always unlock objects after committing changes to avoid
    blocking other team members.
    
    Args:
        project_id: UUID of the project
        lock_id: UUID of the lock to release
        db: Database session dependency
        
    Returns:
        No content (204 status code)
        
    Raises:
        HTTPException 404: If lock doesn't exist or doesn't belong to this project
        
    Example:
        DELETE /api/projects/123e4567-e89b-12d3-a456-426614174000/locks/lock-uuid
    """
    # Fetch the lock to delete
    lock = await db.get(ObjectLock, lock_id)
    if not lock or lock.project_id != project_id:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    # Remove the lock, freeing the object for other users
    await db.delete(lock)
    await db.commit()

# ============== Merge Conflict Routes ==============

@router.get("/{project_id}/conflicts", response_model=List[MergeConflictResponse])
async def get_unresolved_conflicts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all unresolved merge conflicts in a project.
    
    This endpoint retrieves conflicts that occur when merging branches. Conflicts
    happen when the same object is modified differently in two branches. Similar
    to Git merge conflicts, these must be manually resolved by choosing which
    version to keep or manually merging the changes.
    
    Conflicts are tracked to ensure they don't get overlooked during merges.
    
    Args:
        project_id: UUID of the project
        db: Database session dependency
        
    Returns:
        List[MergeConflictResponse]: All unresolved conflicts, oldest first
        
    Example:
        GET /api/projects/123e4567-e89b-12d3-a456-426614174000/conflicts
        
        Response:
        [
            {
                "conflict_id": "uuid",
                "object_name": "Cube",
                "source_branch_id": "branch-1-uuid",
                "target_branch_id": "branch-2-uuid",
                "resolved": false,
                "created_at": "2025-12-02T10:00:00"
            }
        ]
    """
    # Query only unresolved conflicts for this project
    query = (
        select(MergeConflict)
        .where(
            MergeConflict.project_id == project_id,
            MergeConflict.resolved == False  # Only show pending conflicts
        )
        .order_by(MergeConflict.created_at)  # Oldest conflicts first (priority)
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.put("/{project_id}/conflicts/{conflict_id}", response_model=MergeConflictResponse)
async def resolve_conflict(
    project_id: UUID,
    conflict_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a merge conflict as resolved.
    
    This endpoint marks a conflict as resolved after a user manually resolves it.
    Resolution typically involves:
    1. Reviewing both versions of the conflicting object
    2. Deciding which version to keep or manually merging changes
    3. Creating a new commit with the resolved object
    4. Marking the conflict as resolved via this endpoint
    
    This is similar to 'git add' after manually fixing merge conflicts.
    
    Args:
        project_id: UUID of the project
        conflict_id: UUID of the conflict to mark as resolved
        db: Database session dependency
        
    Returns:
        MergeConflictResponse: Updated conflict with resolved=true
        
    Raises:
        HTTPException 404: If conflict doesn't exist or doesn't belong to this project
        
    Example:
        PUT /api/projects/123e4567-e89b-12d3-a456-426614174000/conflicts/conflict-uuid
        
        Response:
        {
            "conflict_id": "uuid",
            "resolved": true,
            "resolved_at": "2025-12-02T15:30:00"
        }
    """
    # Fetch the conflict to resolve
    conflict = await db.get(MergeConflict, conflict_id)
    if not conflict or conflict.project_id != project_id:
        raise HTTPException(status_code=404, detail="Conflict not found")
    
    # Mark as resolved (user has manually fixed the conflict)
    conflict.resolved = True
    await db.commit()
    await db.refresh(conflict)  # Get updated timestamp if any
    return conflict


# ============== Project Collaboration Routes ==============

@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: UUID,
    member_data: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add a user to a project by email address (immediate access, no invitation).
    
    This endpoint allows project owners and existing members to add other users
    to collaborate on a project. The user is granted immediate access without
    requiring invitation acceptance.
    
    **FRONTEND INTEGRATION POINT:**
    When user clicks "Add Member" or "Invite Collaborator" button:
    
    ```javascript
    // Example frontend code
    const response = await fetch(`/api/projects/${projectId}/members`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            email: 'teammate@example.com'
        })
    });
    ```
    
    **Blender Add-on Integration:**
    When users log into the Blender add-on, the GET /api/projects endpoint
    will automatically return all projects they've been added to.
    
    Args:
        project_id: UUID of the project to add member to
        member_data: Contains the email address of user to add
        db: Database session dependency
        current_user: Authenticated user (must be owner or existing member)
        
    Returns:
        ProjectMemberResponse: Details of the newly added member
        
    Raises:
        HTTPException 403: If current user doesn't have permission to add members
        HTTPException 404: If project or user (by email) doesn't exist
        HTTPException 409: If user is already a member of the project
        
    Example Request:
        POST /api/projects/123e4567-e89b-12d3-a456-426614174000/members
        Headers: Authorization: Bearer <token>
        {
            "email": "colleague@example.com"
        }
        
    Example Response:
        {
            "member_id": "uuid",
            "project_id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "user-uuid",
            "username": "colleague_username",
            "email": "colleague@example.com",
            "role": "member",
            "added_at": "2025-12-05T10:30:00",
            "added_by": "current-user-uuid"
        }
    """
    # Step 1: Check if current user has access to this project
    # Only owners and existing members can add new members
    project, user_role = await check_project_access(
        project_id, 
        current_user.user_id, 
        db, 
        require_owner=False  # Members can also add other members
    )
    
    # Step 2: Find the user to add by email
    query = select(User).where(User.email == member_data.email)
    result = await db.execute(query)
    user_to_add = result.scalars().first()
    
    if not user_to_add:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user found with email: {member_data.email}"
        )
    
    # Step 3: Check if user is already a member
    if user_to_add.user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already the project owner"
        )
    
    existing_member_query = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_to_add.user_id
    )
    existing_result = await db.execute(existing_member_query)
    existing_member = existing_result.scalars().first()
    
    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this project"
        )
    
    # Step 4: Add the user as a member
    new_member = ProjectMember(
        project_id=project_id,
        user_id=user_to_add.user_id,
        role="member",
        added_by=current_user.user_id
    )
    db.add(new_member)
    await db.commit()
    await db.refresh(new_member)
    
    # Step 5: Build response with user information
    response = ProjectMemberResponse(
        member_id=new_member.member_id,
        project_id=new_member.project_id,
        user_id=new_member.user_id,
        username=user_to_add.username,
        email=user_to_add.email,
        role=new_member.role,
        added_at=new_member.added_at,
        added_by=new_member.added_by
    )
    
    return response


@router.get("/{project_id}/members", response_model=List[ProjectMemberResponse])
async def get_project_members(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all members of a project.
    
    Returns a list of all users who have access to the project, including
    the owner and all added members.
    
    **FRONTEND INTEGRATION POINT:**
    Use this to display the "Members" or "Collaborators" list in your project settings.
    
    Args:
        project_id: UUID of the project
        db: Database session dependency
        current_user: Authenticated user (must have access to project)
        
    Returns:
        List[ProjectMemberResponse]: List of all project members with details
        
    Raises:
        HTTPException 403: If current user doesn't have access to project
        HTTPException 404: If project doesn't exist
        
    Example Response:
        [
            {
                "member_id": "uuid1",
                "user_id": "owner-uuid",
                "username": "project_owner",
                "email": "owner@example.com",
                "role": "owner",
                "added_at": "2025-12-01T10:00:00"
            },
            {
                "member_id": "uuid2",
                "user_id": "member-uuid",
                "username": "team_member",
                "email": "member@example.com",
                "role": "member",
                "added_at": "2025-12-05T14:30:00",
                "added_by": "owner-uuid"
            }
        ]
    """
    # Check if user has access to this project
    project, _ = await check_project_access(project_id, current_user.user_id, db)
    
    # Get all members including owner
    query = (
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.added_at.asc())  # Owner first (added earliest)
    )
    result = await db.execute(query)
    members_with_users = result.all()
    
    # Build response list
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
            added_by=member.added_by
        ))
    
    return response


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Remove a member from a project.
    
    Only the project owner can remove members. Members cannot remove themselves
    or other members. The owner cannot be removed.
    
    **FRONTEND INTEGRATION POINT:**
    Add a "Remove" button next to each member in the members list.
    
    ```javascript
    await fetch(`/api/projects/${projectId}/members/${memberId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    });
    ```
    
    Args:
        project_id: UUID of the project
        member_id: UUID of the ProjectMember record to remove
        db: Database session dependency
        current_user: Authenticated user (must be project owner)
        
    Returns:
        204 No Content on successful removal
        
    Raises:
        HTTPException 403: If current user is not the project owner
        HTTPException 404: If member doesn't exist
        HTTPException 409: If trying to remove the owner
        
    Example:
        DELETE /api/projects/123e4567-e89b-12d3-a456-426614174000/members/member-uuid
    """
    # Check if current user is the project owner (only owners can remove members)
    project, user_role = await check_project_access(
        project_id,
        current_user.user_id,
        db,
        require_owner=True  # Only owners can remove members
    )
    
    # Fetch the member to remove
    member = await db.get(ProjectMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this project"
        )
    
    # Prevent removing the owner
    if member.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the project owner. Transfer ownership first or delete the project."
        )
    
    # Remove the member
    await db.delete(member)
    await db.commit()
    
    return None  # 204 No Content

