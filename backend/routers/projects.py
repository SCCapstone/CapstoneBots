from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from uuid import UUID
import hashlib
from datetime import datetime

from database import get_db
from models import Project, Branch, Commit, BlenderObject, ObjectLock, MergeConflict
from schemas import (
    ProjectCreate, ProjectResponse, ProjectUpdate, ProjectBase,
    BranchCreate, BranchResponse,
    CommitCreate, CommitResponse, CommitCreateRequest,
    BlenderObjectCreate, BlenderObjectResponse,
    ObjectLockCreate, ObjectLockResponse,
    MergeConflictResponse
)

router = APIRouter()

# ============== Project Routes ==============

@router.get("/", response_model=List[ProjectResponse])
async def get_projects(db: AsyncSession = Depends(get_db)):
    """Get all projects."""
    query = select(Project).order_by(Project.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new project."""
    new_project = Project(**project.dict())
    db.add(new_project)
    await db.flush()
    
    # Create default main branch
    main_branch = Branch(
        project_id=new_project.project_id,
        branch_name="main",
        created_by=new_project.owner_id
    )
    db.add(main_branch)
    await db.commit()
    await db.refresh(new_project)
    return new_project

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific project by ID."""
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
    """Update a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(project, key, value)
    
    await db.commit()
    await db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    await db.delete(project)
    await db.commit()

# ============== Branch Routes ==============

@router.get("/{project_id}/branches", response_model=List[BranchResponse])
async def get_project_branches(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all branches for a project."""
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
    branch: BranchCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new branch in a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    new_branch = Branch(
        project_id=project_id,
        **branch.dict()
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
    """Get commit history for a project/branch (like git log)."""
    query = (
        select(Commit)
        .join(Branch)
        .where(
            Commit.project_id == project_id,
            Branch.branch_name == branch_name
        )
        .options(joinedload(Commit.author))
        .order_by(Commit.committed_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().unique().all()

@router.post("/{project_id}/commits", response_model=CommitResponse, status_code=status.HTTP_201_CREATED)
async def create_commit(
    project_id: UUID,
    data: CommitCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new commit with objects."""
    branch = await db.get(Branch, data.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    # Generate commit hash
    commit_content = f"{project_id}{data.branch_id}{data.author_id}{data.commit_message}{datetime.utcnow()}"
    commit_hash = hashlib.sha256(commit_content.encode()).hexdigest()
    
    new_commit = Commit(
        project_id=project_id,
        branch_id=data.branch_id,
        parent_commit_id=branch.head_commit_id,
        author_id=data.author_id,
        commit_message=data.commit_message,
        commit_hash=commit_hash,
        committed_at=datetime.utcnow()
    )
    db.add(new_commit)
    await db.flush()
    
    # Add objects to commit
    for obj_data in data.objects:
        blender_obj = BlenderObject(
            commit_id=new_commit.commit_id,
            **obj_data.dict()
        )
        db.add(blender_obj)
    
    # Update branch HEAD
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
    """Get all objects in a specific commit (like git show)."""
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
    db: AsyncSession = Depends(get_db)
):
    """Get all active locks in a project."""
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
    db: AsyncSession = Depends(get_db)
):
    """Lock an object to prevent concurrent edits."""
    # Check if already locked
    existing_lock = (
        select(ObjectLock)
        .where(
            ObjectLock.project_id == project_id,
            ObjectLock.object_name == lock_data.object_name,
            ObjectLock.branch_id == lock_data.branch_id
        )
    )
    result = await db.execute(existing_lock)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Object is already locked")
    
    new_lock = ObjectLock(
        project_id=project_id,
        object_name=lock_data.object_name,
        locked_by=lock_data.locked_by,
        branch_id=lock_data.branch_id,
        expires_at=lock_data.expires_at
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
    """Release a lock on an object."""
    lock = await db.get(ObjectLock, lock_id)
    if not lock or lock.project_id != project_id:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    await db.delete(lock)
    await db.commit()

# ============== Merge Conflict Routes ==============

@router.get("/{project_id}/conflicts", response_model=List[MergeConflictResponse])
async def get_unresolved_conflicts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all unresolved merge conflicts in a project."""
    query = (
        select(MergeConflict)
        .where(
            MergeConflict.project_id == project_id,
            MergeConflict.resolved == False
        )
        .order_by(MergeConflict.created_at)
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.put("/{project_id}/conflicts/{conflict_id}", response_model=MergeConflictResponse)
async def resolve_conflict(
    project_id: UUID,
    conflict_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Mark a conflict as resolved."""
    conflict = await db.get(MergeConflict, conflict_id)
    if not conflict or conflict.project_id != project_id:
        raise HTTPException(status_code=404, detail="Conflict not found")
    
    conflict.resolved = True
    await db.commit()
    await db.refresh(conflict)
    return conflict
