"""
Storage and Versioning Routes

Handles file storage, retrieval, and version management for CapstoneBots.
Provides endpoints for:
- Uploading Blender objects to MinIO
- Downloading commits and objects
- Viewing version history with storage info
- Managing project storage
"""

from typing import List
from uuid import UUID
import hashlib
import json
from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
import io
from minio.error import S3Error

from database import get_db
from models import Project, Commit, BlenderObject, Branch
from schemas import (
    CommitResponse, BlenderObjectResponse, StorageObjectInfo,
    ProjectStorageStats, VersionHistoryResponse, ObjectDownloadResponse
)
from storage.storage_service import StorageService, get_storage_service
from utils.auth import get_current_user
from models import User

router = APIRouter()
logger = logging.getLogger(__name__)


# ============== Object Upload Routes ==============

@router.post("/{project_id}/objects/upload", status_code=status.HTTP_201_CREATED)
async def upload_blender_object(
    project_id: UUID,
    object_id: UUID,
    commit_hash: str,
    object_name: str,
    object_type: str,
    json_file: UploadFile = File(...),
    mesh_file: UploadFile = None,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a Blender object with optional mesh data to storage.
    
    This endpoint handles file uploads for Blender objects, storing both
    metadata (JSON) and optional binary mesh data to MinIO. Files are
    organized by project → object → commit hash.
    
    Args:
        project_id: Target project UUID
        object_id: Object UUID
        commit_hash: Associated commit hash
        object_name: Human-readable object name
        object_type: Blender object type (MESH, CAMERA, LIGHT, etc.)
        json_file: Object metadata as JSON file
        mesh_file: Optional binary mesh data
        db: Database session
        storage: Storage service
        current_user: Authenticated user
        
    Returns:
        dict: Storage paths and metadata for uploaded files
        
    Example:
        POST /api/projects/{project_id}/objects/upload?object_id=...&commit_hash=...
        Files:
        - json_file: metadata.json
        - mesh_file: mesh.bin (optional)
    """
    # Verify project exists and user has access
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to upload to this project")
    
    # Read and parse JSON metadata
    json_content = await json_file.read()
    try:
        json_data = json.loads(json_content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in json_file")
    
    # Upload JSON metadata
    json_path = storage.upload_object_json(project_id, object_id, commit_hash, json_data)
    
    # Upload mesh data if provided
    mesh_path = None
    if mesh_file:
        mesh_content = await mesh_file.read()
        mesh_path = storage.upload_object_mesh(project_id, object_id, commit_hash, mesh_content)
    
    # Calculate blob hash for deduplication
    blob_hash = storage.compute_blob_hash(json_data)
    
    return {
        "object_id": str(object_id),
        "object_name": object_name,
        "object_type": object_type,
        "json_path": json_path,
        "mesh_path": mesh_path,
        "blob_hash": blob_hash,
        "json_size": len(json_content),
        "mesh_size": len(mesh_content) if mesh_file else None,
    }


# ============== Object Download Routes ==============

@router.get("/{project_id}/commits/{commit_id}/download", response_class=StreamingResponse)
async def download_commit(
    project_id: UUID,
    commit_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Download a complete commit as a JSON file.
    
    Reconstructs the full state of a commit by retrieving all stored objects
    from MinIO and compiling them into a single JSON file for download.
    
    Args:
        project_id: Project UUID
        commit_id: Commit UUID to download
        db: Database session
        storage: Storage service
        current_user: Authenticated user
        
    Returns:
        StreamingResponse: Complete commit data as JSON
        
    Example:
        GET /api/projects/{project_id}/commits/{commit_id}/download
        
        Downloads: commit_2025-12-04T10-30-00.json
    """
    # Verify commit exists and belongs to project
    commit = await db.get(Commit, commit_id)
    if not commit or commit.project_id != project_id:
        raise HTTPException(status_code=404, detail="Commit not found")
    
    # Verify user has access to project
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to download from this project")
    
    # Retrieve all objects in commit
    result = await db.execute(
        select(BlenderObject)
        .where(BlenderObject.commit_id == commit_id)
        .order_by(BlenderObject.object_name)
    )
    blender_objects = result.scalars().all()
    
    # Reconstruct commit data from storage
    commit_data = {
        "commit_id": str(commit.commit_id),
        "commit_hash": commit.commit_hash,
        "commit_message": commit.commit_message,
        "author_id": str(commit.author_id),
        "committed_at": commit.committed_at.isoformat(),
        "objects": []
    }
    
    # Fetch each object from storage
    for obj in blender_objects:
        try:
            json_data = storage.download_object_json(obj.json_data_path)
            obj_entry = {
                "object_id": str(obj.object_id),
                "object_name": obj.object_name,
                "object_type": obj.object_type,
                "data": json_data,
                "blob_hash": obj.blob_hash,
            }
            
            # Include mesh if available
            if obj.mesh_data_path:
                try:
                    # Don't include binary mesh in JSON - return path instead for download
                    obj_entry["mesh_path"] = obj.mesh_data_path
                    obj_entry["mesh_size"] = storage.get_object_size(obj.mesh_data_path)
                except Exception as e:
                    # Mesh may not exist, continue without it
                    pass
            
            commit_data["objects"].append(obj_entry)
        except Exception as e:
            # Log error but continue with other objects
            print(f"Error retrieving object {obj.object_id}: {e}")
            continue
    
    # Serialize to JSON bytes
    json_bytes = json.dumps(commit_data, indent=2).encode('utf-8')
    
    # Return as file download
    return StreamingResponse(
        iter([json_bytes]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="commit_{commit.commit_hash[:8]}_{commit.committed_at.isoformat()}.json"'
        }
    )


@router.get("/{project_id}/commits/{commit_id}/objects/{object_id}/download", response_class=FileResponse)
async def download_object(
    project_id: UUID,
    commit_id: UUID,
    object_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Download a specific Blender object metadata (JSON).
    
    Args:
        project_id: Project UUID
        commit_id: Commit UUID
        object_id: Object UUID
        db: Database session
        storage: Storage service
        current_user: Authenticated user
        
    Returns:
        FileResponse: Object JSON data as download
    """
    # Verify object exists
    obj = await db.get(BlenderObject, object_id)
    if not obj or obj.commit_id != commit_id:
        raise HTTPException(status_code=404, detail="Object not found in commit")
    
    # Verify access
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Download object data
    try:
        json_data = storage.download_object_json(obj.json_data_path)
        json_bytes = json.dumps(json_data, indent=2).encode('utf-8')
        
        return StreamingResponse(
            iter([json_bytes]),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{obj.object_name}_{obj.blob_hash[:8]}.json"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading object: {str(e)}")


@router.get("/{project_id}/files/download")
async def get_signed_url(
    project_id: UUID,
    path: str,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get a presigned URL to download a file securely.
    
    This replaces the insecure generic download endpoint.
    It verifies that the user has access to the project and that
    the requested file belongs to the project.
    """
    # Verify access
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Normalize path and perform security check to ensure it belongs to this project
    normalized_path = path or ""
    
    # Handle full S3 URLs like "s3://bucket/key..."
    if normalized_path.startswith("s3://"):
        # Strip scheme
        without_scheme = normalized_path[5:]
        # Remove bucket name (up to first "/"), leaving just the key
        first_slash = without_scheme.find("/")
        if first_slash != -1:
            normalized_path = without_scheme[first_slash + 1:]
        else:
            normalized_path = ""
    
    # Security check: Ensure path belongs to this project
    # Allow both "projects/{project_id}/..." and "{project_id}/..." formats
    expected_prefixes = [
        f"projects/{project_id}/",
        f"{project_id}/",
    ]
    if not any(normalized_path.startswith(prefix) for prefix in expected_prefixes):
        raise HTTPException(
            status_code=403,
            detail="Invalid file path for this project",
        )
    
    try:
        url = storage.get_presigned_url(normalized_path)
        return {"url": url}
    except S3Error as e:
        logger.error(f"S3 error generating presigned URL: {e}")
        # Check if object doesn't exist
        if e.code == "NoSuchKey":
            raise HTTPException(status_code=404, detail="File not found")
        raise HTTPException(status_code=500, detail="Error generating download URL")
    except Exception as e:
        logger.error(f"Unexpected error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Error generating download URL")


# ============== Version History & Storage Stats ==============

@router.get("/{project_id}/versions", response_model=List[VersionHistoryResponse])
async def get_version_history(
    project_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get version history for a project with storage information.
    
    Lists all commits in a project with information about their snapshots
    stored in object storage, ordered by most recent first.
    
    Args:
        project_id: Project UUID
        limit: Maximum number of versions to return (default 50)
        db: Database session
        storage: Storage service
        current_user: Authenticated user
        
    Returns:
        List[VersionHistoryResponse]: Version history with storage info
    """
    # Verify access
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get commits
    result = await db.execute(
        select(Commit)
        .where(Commit.project_id == project_id)
        .options(joinedload(Commit.author))
        .order_by(Commit.committed_at.desc())
        .limit(limit)
    )
    commits = result.scalars().unique().all()
    
    # Build response with storage info
    history = []
    for commit in commits:
        # Check if snapshot exists
        snapshot_path = storage.get_snapshot_path(project_id, commit.commit_hash, commit.committed_at)
        snapshot_size = None
        
        try:
            if storage.object_exists(snapshot_path):
                snapshot_size = storage.get_object_size(snapshot_path)
        except:
            pass
        
        history.append(VersionHistoryResponse(
            commit_id=commit.commit_id,
            commit_hash=commit.commit_hash,
            commit_message=commit.commit_message,
            author_id=commit.author_id,
            committed_at=commit.committed_at,
            snapshot_path=snapshot_path if snapshot_size else None,
            snapshot_size=snapshot_size,
        ))
    
    return history


@router.get("/{project_id}/storage-stats", response_model=ProjectStorageStats)
async def get_storage_stats(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get storage usage statistics for a project.
    
    Returns breakdown of storage usage including total size, object storage,
    and version snapshots.
    
    Args:
        project_id: Project UUID
        db: Database session
        storage: Storage service
        current_user: Authenticated user
        
    Returns:
        ProjectStorageStats: Storage breakdown
    """
    # Verify access
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Calculate storage
    try:
        stats = storage.estimate_project_storage(project_id)
        return ProjectStorageStats(
            project_id=project_id,
            **stats
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating storage: {str(e)}")


# ============== Snapshot Management ==============

@router.post("/{project_id}/commits/{commit_id}/snapshot", status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    project_id: UUID,
    commit_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a full .blend file snapshot for a commit.
    
    Allows archiving complete Blender project files alongside the decomposed
    object data for full recovery capability.
    
    Args:
        project_id: Project UUID
        commit_id: Commit UUID
        file: .blend file to snapshot
        db: Database session
        storage: Storage service
        current_user: Authenticated user
        
    Returns:
        dict: Snapshot storage information
    """
    # Verify commit exists
    commit = await db.get(Commit, commit_id)
    if not commit or commit.project_id != project_id:
        raise HTTPException(status_code=404, detail="Commit not found")
    
    # Verify access
    project = await db.get(Project, project_id)
    if not project or project.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Upload snapshot
    blend_content = await file.read()
    try:
        snapshot_path = storage.upload_snapshot(
            project_id,
            commit.commit_hash,
            commit.committed_at,
            blend_content
        )
        
        return {
            "commit_id": str(commit_id),
            "snapshot_path": snapshot_path,
            "file_size": len(blend_content),
            "file_size_mb": round(len(blend_content) / (1024 * 1024), 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading snapshot: {str(e)}")
