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
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import joinedload

from database import get_db
from models import (
    Project, Branch, Commit, BlenderObject, ObjectLock, MergeConflict,
    User, ProjectMember, ProjectInvitation,
    MemberRole, InvitationStatus, INVITE_EXPIRY_DAYS, role_at_least,
)
from schemas import (
    ProjectCreate, ProjectResponse, ProjectUpdate, ProjectBase,
    BranchCreate, BranchResponse,
    CommitCreate, CommitResponse, CommitCreateRequest,
    BlenderObjectCreate, BlenderObjectResponse,
    ObjectLockCreate, ObjectLockResponse,
    MergeConflictResponse,
    ProjectMemberAdd, ProjectMemberResponse, ProjectMemberRemove, ProjectWithMembersResponse,
    InvitationCreate, InvitationResponse, MemberRoleUpdate,
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

    # Delete S3 objects linked to this project's blender_objects
    from sqlalchemy import text as sa_text
    pid = str(project_id)
    try:
        # Gather all S3 paths from blender_objects via commits
        s3_rows = await db.execute(sa_text(
            "SELECT bo.json_data_path, bo.mesh_data_path FROM blender_objects bo "
            "JOIN commits c ON bo.commit_id = c.commit_id "
            "WHERE c.project_id = :pid"
        ), {"pid": pid})
        s3_paths = []
        for row in s3_rows:
            for path in (row[0], row[1]):
                if path and isinstance(path, str) and path.startswith("s3://"):
                    s3_paths.append(path)

        if s3_paths:
            import os, boto3
            s3_client = boto3.client(
                "s3",
                region_name=os.environ.get("S3_REGION", "us-east-1"),
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("S3_ACCESS_KEY"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("S3_SECRET_KEY"),
            )
            # Group by bucket and batch delete (max 1000 per request)
            from collections import defaultdict
            bucket_keys: dict[str, list[str]] = defaultdict(list)
            for s3_uri in s3_paths:
                parts = s3_uri[5:]  # strip "s3://"
                slash = parts.find("/")
                if slash > 0:
                    bucket_keys[parts[:slash]].append(parts[slash + 1:])
            for bucket, keys in bucket_keys.items():
                for i in range(0, len(keys), 1000):
                    batch = keys[i:i + 1000]
                    s3_client.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
                    )
            import logging
            logging.getLogger(__name__).info(f"Deleted {len(s3_paths)} S3 objects for project {project_id}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"S3 cleanup failed for project {project_id}: {e}")

    # Use raw SQL to avoid ORM circular dependency between Branch ↔ Commit
    await db.execute(sa_text("UPDATE branches SET head_commit_id = NULL WHERE project_id = :pid"), {"pid": pid})
    await db.execute(sa_text("UPDATE commits SET parent_commit_id = NULL WHERE project_id = :pid"), {"pid": pid})
    await db.execute(sa_text(
        "UPDATE blender_objects SET parent_object_id = NULL "
        "WHERE commit_id IN (SELECT commit_id FROM commits WHERE project_id = :pid)"
    ), {"pid": pid})
    await db.execute(sa_text(
        "DELETE FROM blender_objects "
        "WHERE commit_id IN (SELECT commit_id FROM commits WHERE project_id = :pid)"
    ), {"pid": pid})

    for tbl in [
        "object_locks", "merge_conflicts",
        "commits", "branches", "project_metadata",
        "project_invitations", "project_members",
    ]:
        await db.execute(sa_text(f"DELETE FROM {tbl} WHERE project_id = :pid"), {"pid": pid})

    await db.execute(sa_text("DELETE FROM projects WHERE project_id = :pid"), {"pid": pid})
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
        expires_at=datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS),
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
    Add a user to a project by email address (immediate access, no invitation required).

    For invitation-based workflows, use POST /{project_id}/invitations instead.
    """
    # Validate role
    role = member_data.role or MemberRole.editor.value
    if role not in [r.value for r in MemberRole]:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    project, _ = await check_project_access(
        project_id, current_user.user_id, db, require_role=MemberRole.editor
    )

    # Resolve user by email or username
    if not member_data.email and not member_data.username:
        raise HTTPException(status_code=400, detail="Provide either email or username.")

    if member_data.email:
        result = await db.execute(select(User).where(User.email == member_data.email))
    else:
        result = await db.execute(select(User).where(User.username == member_data.username))
    user_to_add = result.scalars().first()

    if not user_to_add:
        raise HTTPException(status_code=404, detail="No user found with that email or username.")

    # Check if already the project owner
    if user_to_add.user_id == project.owner_id:
        raise HTTPException(status_code=409, detail="User is already the project owner.")

    # Check if already a member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_to_add.user_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="User is already a member of this project.")

    # Add the user directly as a member
    new_member = ProjectMember(
        project_id=project_id,
        user_id=user_to_add.user_id,
        role=role,
        added_by=current_user.user_id,
    )
    db.add(new_member)
    await db.commit()
    await db.refresh(new_member)

    return ProjectMemberResponse(
        member_id=new_member.member_id,
        project_id=new_member.project_id,
        user_id=user_to_add.user_id,
        username=user_to_add.username,
        email=user_to_add.email,
        role=new_member.role,
        added_at=new_member.added_at,
        added_by=new_member.added_by,
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

