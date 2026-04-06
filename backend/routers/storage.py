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
from models import Commit, BlenderObject, User, MemberRole
from schemas import (
    CommitResponse, BlenderObjectResponse, StorageObjectInfo,
    ProjectStorageStats, VersionHistoryResponse, ObjectDownloadResponse
)
from storage.storage_service import StorageService, get_storage_service
from utils.auth import get_current_user
from utils.permissions import check_project_access

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
    organized by project → object → commit hash. Requires the commit
    to already exist in the database.

    For uploading objects *before* creating a commit (object-level VCS flow),
    use the ``stage-upload`` endpoint instead.
    """
    # Editors and above can upload objects
    await check_project_access(project_id, current_user.user_id, db, require_role=MemberRole.editor)

    # Resolve commit_hash → Commit row to get the UUID FK
    result = await db.execute(
        select(Commit).where(
            Commit.project_id == project_id,
            Commit.commit_hash == commit_hash
        )
    )
    commit = result.scalar_one_or_none()
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")

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
    mesh_content = None
    if mesh_file:
        mesh_content = await mesh_file.read()
        mesh_path = storage.upload_object_mesh(project_id, object_id, commit_hash, mesh_content)

    # Calculate blob hash for deduplication
    blob_hash = storage.compute_blob_hash(json_data)

    # Insert BlenderObject DB record; clean up S3 on failure to prevent orphans
    try:
        db_object = BlenderObject(
            object_id=object_id,
            commit_id=commit.commit_id,
            object_name=object_name,
            object_type=object_type,
            json_data_path=json_path,
            mesh_data_path=mesh_path,
            blob_hash=blob_hash,
        )
        db.add(db_object)
        await db.commit()
    except Exception as e:
        try:
            storage.delete_object(json_path)
            if mesh_path:
                storage.delete_object(mesh_path)
        except Exception:
            pass
        logger.error("DB insert failed for object %s: %s", object_id, e)
        raise HTTPException(status_code=500, detail="Failed to record object in database")

    return {
        "object_id": str(object_id),
        "object_name": object_name,
        "object_type": object_type,
        "json_path": json_path,
        "mesh_path": mesh_path,
        "blob_hash": blob_hash,
        "json_size": len(json_content),
        "mesh_size": len(mesh_content) if mesh_content is not None else None,
    }


@router.post("/{project_id}/objects/stage-upload", status_code=status.HTTP_201_CREATED)
async def stage_upload_blender_object(
    project_id: UUID,
    object_name: str,
    object_type: str,
    blob_hash: str,
    json_file: UploadFile = File(...),
    mesh_file: UploadFile = None,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a Blender object to S3 storage *before* creating a commit.

    This is used by the object-level VCS flow where the addon:
    1. Serializes each changed object
    2. Uploads JSON metadata + optional mesh binary to S3 via this endpoint
    3. Creates the commit via POST /commits with the returned S3 paths

    Unlike ``/objects/upload``, this endpoint does NOT require a commit to
    exist and does NOT insert a BlenderObject DB row. The commit creation
    endpoint handles DB record creation.

    The blob_hash is used as the S3 path component (instead of commit_hash)
    so that identical content maps to the same path for deduplication.

    Args:
        project_id: Target project UUID
        object_name: Human-readable object name (e.g. "Cube")
        object_type: Blender object type (MESH, CAMERA, LIGHT, etc.)
        blob_hash: SHA-256 hash of the object metadata (used for dedup and S3 path)
        json_file: Object metadata as JSON file
        mesh_file: Optional binary mesh data

    Returns:
        dict with json_path, mesh_path, blob_hash, sizes
    """
    await check_project_access(project_id, current_user.user_id, db, require_role=MemberRole.editor)

    # Validate object_name
    if not object_name or not object_name.strip():
        raise HTTPException(status_code=400, detail="object_name is required")

    # Validate blob_hash
    if not blob_hash or len(blob_hash) != 64:
        raise HTTPException(status_code=400, detail="blob_hash must be a 64-character hex string")

    # Read JSON content
    json_content = await json_file.read()
    try:
        json_data = json.loads(json_content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in json_file")

    # Use blob_hash as the "commit hash" path component for S3 organization.
    # This means identical content always goes to the same path → natural dedup.
    from uuid import uuid4
    object_id = uuid4()

    json_path = storage.upload_object_json(project_id, object_id, blob_hash, json_data)

    mesh_path = None
    mesh_size = None
    if mesh_file:
        mesh_content = await mesh_file.read()
        mesh_path = storage.upload_object_mesh(project_id, object_id, blob_hash, mesh_content)
        mesh_size = len(mesh_content)

    return {
        "object_name": object_name,
        "object_type": object_type,
        "json_path": json_path,
        "mesh_path": mesh_path,
        "blob_hash": blob_hash,
        "json_size": len(json_content),
        "mesh_size": mesh_size,
    }


@router.get("/{project_id}/objects/download-url")
async def get_object_download_url(
    project_id: UUID,
    path: str,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get a presigned download URL for an object's JSON metadata or mesh binary.

    This is a simplified version of the ``/files/download`` endpoint,
    specifically for object-level VCS. It validates that the requested path
    belongs to the project and returns a presigned URL.

    Args:
        project_id: Project UUID
        path: S3 object path (e.g. "projects/{project_id}/objects/{object_id}/hash.json")

    Returns:
        dict with "url" key containing the presigned download URL
    """
    await check_project_access(project_id, current_user.user_id, db)

    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="path is required")

    normalized = path.strip()

    # Security: ensure path belongs to this project
    expected_prefix = f"projects/{project_id}/"
    if not normalized.startswith(expected_prefix):
        raise HTTPException(status_code=403, detail="Path does not belong to this project")

    try:
        url = storage.get_presigned_url(normalized)
        return {"url": url}
    except S3Error as e:
        if e.code == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Object not found in storage")
        logger.error(f"S3 error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Error generating download URL")
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Error generating download URL")


@router.get("/{project_id}/objects/content")
async def get_object_content(
    project_id: UUID,
    path: str,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_user),
):
    """
    Proxy-download raw file content from S3 by path.

    Unlike ``download-url`` (which returns a presigned URL), this streams the
    actual bytes through the backend so the browser never hits S3 directly —
    avoiding CORS issues for in-browser processing like GLB export.
    """
    await check_project_access(project_id, current_user.user_id, db)

    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="path is required")

    normalized = path.strip()
    expected_prefix = f"projects/{project_id}/"
    if not normalized.startswith(expected_prefix):
        raise HTTPException(status_code=403, detail="Path does not belong to this project")

    try:
        if normalized.endswith(".json"):
            json_data = storage.download_object_json(normalized)
            data = json.dumps(json_data).encode("utf-8")
            media_type = "application/json"
        else:
            data = storage.download_object_mesh(normalized)
            media_type = "application/octet-stream"
        return StreamingResponse(
            iter([data]),
            media_type=media_type,
        )
    except S3Error as e:
        if e.code == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Object not found in storage")
        logger.error(f"S3 error downloading content: {e}")
        raise HTTPException(status_code=500, detail="Error downloading content")
    except Exception as e:
        logger.error(f"Error downloading content: {e}")
        raise HTTPException(status_code=500, detail="Error downloading content")


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
    # Verify access (any member can download)
    await check_project_access(project_id, current_user.user_id, db)

    # Verify commit exists and belongs to project
    commit = await db.get(Commit, commit_id)
    if not commit or commit.project_id != project_id:
        raise HTTPException(status_code=404, detail="Commit not found")
    
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
            logger.error("Error retrieving object %s: %s", obj.object_id, e)
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
    # Any member can download objects
    await check_project_access(project_id, current_user.user_id, db)

    # Verify object exists
    obj = await db.get(BlenderObject, object_id)
    if not obj or obj.commit_id != commit_id:
        raise HTTPException(status_code=404, detail="Object not found in commit")
    
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
    # Any member can generate presigned URLs for project files
    await check_project_access(project_id, current_user.user_id, db)

    # Validate path is provided
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="File path is required")
    
    # Normalize path and perform security check to ensure it belongs to this project
    normalized_path = path.strip()
    
    # Handle full S3 URLs like "s3://bucket/key..."
    if normalized_path.startswith("s3://"):
        # Strip scheme
        without_scheme = normalized_path[5:]
        # Remove bucket name (up to first "/"), leaving just the key
        first_slash = without_scheme.find("/")
        if first_slash != -1:
            normalized_path = without_scheme[first_slash + 1:]
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid S3 URL format: expected s3://bucket/key/path but no key path found"
            )
    
    # Security check: Ensure path belongs to this project
    # Accept "projects/{project_id}/...", "{project_id}/...", and "{project_id}_..." formats
    # The underscore variant is used for .blend file uploads: "{project_id}_{timestamp}/file.blend"
    expected_prefixes = [
        f"projects/{project_id}/",
        f"projects/{project_id}_",
        f"{project_id}/",
        f"{project_id}_",
    ]
    if not normalized_path or not any(normalized_path.startswith(prefix) for prefix in expected_prefixes):
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
        # Check for permission issues
        if e.code == "AccessDenied":
            raise HTTPException(status_code=403, detail="Access denied to file")
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
    # Any member can view version history
    await check_project_access(project_id, current_user.user_id, db)

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
        except Exception:
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
    # Any member can view storage stats
    await check_project_access(project_id, current_user.user_id, db)

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
    # Editors and above can upload snapshots
    await check_project_access(project_id, current_user.user_id, db, require_role=MemberRole.editor)

    # Verify commit exists and belongs to project
    commit = await db.get(Commit, commit_id)
    if not commit or commit.project_id != project_id:
        raise HTTPException(status_code=404, detail="Commit not found")
    
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
