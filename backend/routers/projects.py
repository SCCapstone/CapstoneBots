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
from models import Project, Branch, Commit, BlenderObject, ObjectLock, MergeConflict, User
from schemas import (
    ProjectCreate, ProjectResponse, ProjectUpdate, ProjectBase,
    BranchCreate, BranchResponse,
    CommitCreate, CommitResponse, CommitCreateRequest,
    BlenderObjectCreate, BlenderObjectResponse,
    ObjectLockCreate, ObjectLockResponse,
    MergeConflictResponse,
)
from utils.auth import get_current_user

# Initialize the router for project-related endpoints
router = APIRouter()

# ============== Project Routes ==============

@router.get("/", response_model=List[ProjectResponse])
async def get_projects(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Get all projects owned by the authenticated user.
    
    This endpoint retrieves a list of all Blender projects that belong to the
    currently logged-in user, sorted by creation date (newest first).
    
    Args:
        db: Database session dependency
        current_user: Authenticated user from JWT token
        
    Returns:
        List[ProjectResponse]: List of user's projects with metadata
        
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
            }
        ]
    """
    # Query database for all projects owned by the current user
    query = (
        select(Project)
        .where(Project.owner_id == current_user.user_id)
        .order_by(Project.created_at.desc())  # Most recent projects first
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
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
    await db.commit()  # Commit both project and branch together
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
    db: AsyncSession = Depends(get_db)
):
    """
    Get commit history for a branch (similar to 'git log').
    
    This endpoint retrieves all commits in a specific branch, showing the project's
    version history. Each commit represents a snapshot of changes made to Blender
    objects at a specific point in time. Commits are ordered newest first.
    
    Args:
        project_id: UUID of the project
        branch_name: Name of the branch (defaults to 'main')
        db: Database session dependency
        
    Returns:
        List[CommitResponse]: Commit history with author info, newest first
        
    Example:
        GET /api/projects/123e4567-e89b-12d3-a456-426614174000/commits?branch_name=main
        
        Response:
        [
            {
                "commit_id": "uuid",
                "commit_hash": "a3f2e1...",
                "commit_message": "Updated lighting setup",
                "author_id": "user-id",
                "committed_at": "2025-12-02T15:30:00",
                "parent_commit_id": "parent-uuid"
            }
        ]
    """
    # Query commits for the specified branch, join with Branch to filter by name
    # Include author information via joinedload for efficient data fetching
    query = (
        select(Commit)
        .join(Branch)
        .where(
            Commit.project_id == project_id,
            Branch.branch_name == branch_name
        )
        .options(joinedload(Commit.author))  # Eagerly load author data
        .order_by(Commit.committed_at.desc())  # Most recent commits first
    )
    result = await db.execute(query)
    return result.scalars().unique().all()  # unique() prevents duplicate rows from join

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