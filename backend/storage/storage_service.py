"""
Storage Service Layer for MinIO Object Storage

Handles all interactions with MinIO for:
- Uploading Blender objects (JSON metadata and binary mesh data)
- Downloading and retrieving objects by commit hash
- Managing versioned snapshots and deduplication
- Organizing files in a hierarchical structure
"""

import os
import json
import hashlib
import io
from typing import Optional, Tuple, Dict, Any, Union
from datetime import datetime, timedelta
from uuid import UUID
from pathlib import Path

from minio import Minio
from minio.error import S3Error
import logging

logger = logging.getLogger(__name__)

# Maximum hours for presigned URL expiration (7 days)
MAX_PRESIGNED_URL_HOURS = 168


class StorageService:
    """
    Manages all file operations for the versioning system.
    
    Storage hierarchy:
    s3://bucket/
    ├── projects/{project_id}/
    │   ├── versions/
    │   │   └── {timestamp}_{commit_hash[:8]}.blend
    │   ├── objects/
    │   │   └── {object_id}/
    │   │       ├── {commit_hash}.json
    │   │       └── mesh-data/
    │   │           └── {commit_hash}.bin
    │   ├── dedup/
    │   │   └── {blob_hash}.json  (for identical content)
    │   └── metadata/
    │       └── {project_id}.json
    """

    def __init__(self):
        """Initialize MinIO client with credentials from environment"""
        endpoint = os.environ.get("S3_ENDPOINT", "localhost:9000").replace("https://", "").replace("http://", "")
        access_key = os.environ.get("S3_ACCESS_KEY", "minioadmin")
        secret_key = os.environ.get("S3_SECRET_KEY", "minioadmin")
        secure = os.environ.get("S3_SECURE", "true").lower() == "true"
        region = os.environ.get("S3_REGION", "us-east-1")

        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )

        self.bucket_name = os.environ.get("S3_BUCKET", "capstonebots")
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error checking/creating bucket: {e}")
            raise

    # ============== Path Generation Methods ==============

    def _get_project_prefix(self, project_id: UUID) -> str:
        """Get the base prefix for a project"""
        return f"projects/{project_id}"

    def get_object_json_path(self, project_id: UUID, object_id: UUID, commit_hash: str) -> str:
        """
        Get storage path for object metadata (JSON).
        
        Example: projects/{project_id}/objects/{object_id}/{commit_hash}.json
        """
        return f"{self._get_project_prefix(project_id)}/objects/{object_id}/{commit_hash}.json"

    def get_object_mesh_path(self, project_id: UUID, object_id: UUID, commit_hash: str) -> str:
        """
        Get storage path for object mesh data (binary).
        
        Example: projects/{project_id}/objects/{object_id}/mesh-data/{commit_hash}.bin
        """
        return f"{self._get_project_prefix(project_id)}/objects/{object_id}/mesh-data/{commit_hash}.bin"

    def get_dedup_path(self, blob_hash: str) -> str:
        """
        Get storage path for deduplicated content.
        Used when identical JSON content is uploaded multiple times.
        
        Example: projects/dedup/{blob_hash}.json
        """
        return f"projects/dedup/{blob_hash}.json"

    def get_snapshot_path(self, project_id: UUID, commit_hash: str, timestamp: datetime) -> str:
        """
        Get storage path for full blend file snapshot.
        
        Example: projects/{project_id}/versions/{timestamp}_{commit_hash[:8]}.blend
        """
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"{self._get_project_prefix(project_id)}/versions/{ts_str}_{commit_hash[:8]}.blend"

    def get_project_metadata_path(self, project_id: UUID) -> str:
        """Get storage path for project metadata"""
        return f"{self._get_project_prefix(project_id)}/metadata/{project_id}.json"

    # ============== Upload Methods ==============

    def upload_object_json(self, project_id: UUID, object_id: UUID, 
                          commit_hash: str, json_data: Dict[str, Any]) -> str:
        """
        Upload object metadata (JSON) to storage.
        
        Args:
            project_id: Project UUID
            object_id: Blender object UUID
            commit_hash: Commit hash for versioning
            json_data: Object metadata as dictionary
            
        Returns:
            str: Storage path where file was uploaded
        """
        path = self.get_object_json_path(project_id, object_id, commit_hash)
        data_bytes = json.dumps(json_data, indent=2).encode('utf-8')
        
        try:
            self.client.put_object(
                self.bucket_name,
                path,
                io.BytesIO(data_bytes),
                length=len(data_bytes),
                content_type="application/json"
            )
            logger.info(f"Uploaded object JSON: {path}")
            return path
        except S3Error as e:
            logger.error(f"Error uploading object JSON to {path}: {e}")
            raise

    def upload_object_mesh(self, project_id: UUID, object_id: UUID, 
                          commit_hash: str, mesh_data: bytes) -> str:
        """
        Upload object mesh data (binary) to storage.
        
        Args:
            project_id: Project UUID
            object_id: Blender object UUID
            commit_hash: Commit hash for versioning
            mesh_data: Binary mesh data
            
        Returns:
            str: Storage path where file was uploaded
        """
        path = self.get_object_mesh_path(project_id, object_id, commit_hash)
        
        try:
            self.client.put_object(
                self.bucket_name,
                path,
                io.BytesIO(mesh_data),
                length=len(mesh_data),
                content_type="application/octet-stream"
            )
            logger.info(f"Uploaded mesh data: {path}")
            return path
        except S3Error as e:
            logger.error(f"Error uploading mesh data to {path}: {e}")
            raise

    def upload_snapshot(self, project_id: UUID, commit_hash: str, 
                       timestamp: datetime, blend_data: bytes) -> str:
        """
        Upload full blend file snapshot for recovery/archival.
        
        Args:
            project_id: Project UUID
            commit_hash: Commit hash
            timestamp: Commit timestamp
            blend_data: Full blend file binary data
            
        Returns:
            str: Storage path where file was uploaded
        """
        path = self.get_snapshot_path(project_id, commit_hash, timestamp)
        
        try:
            self.client.put_object(
                self.bucket_name,
                path,
                io.BytesIO(blend_data),
                length=len(blend_data),
                content_type="application/octet-stream"
            )
            logger.info(f"Uploaded snapshot: {path}")
            return path
        except S3Error as e:
            logger.error(f"Error uploading snapshot to {path}: {e}")
            raise

    # ============== Download Methods ==============

    def download_object_json(self, path: str) -> Dict[str, Any]:
        """
        Download and deserialize object JSON metadata.
        
        Args:
            path: Storage path to the JSON file
            
        Returns:
            dict: Deserialized JSON data
        """
        try:
            response = self.client.get_object(self.bucket_name, path)
            data = json.loads(response.read().decode('utf-8'))
            logger.info(f"Downloaded object JSON: {path}")
            return data
        except S3Error as e:
            logger.error(f"Error downloading object JSON from {path}: {e}")
            raise

    def download_object_mesh(self, path: str) -> bytes:
        """
        Download object mesh binary data.
        
        Args:
            path: Storage path to the mesh file
            
        Returns:
            bytes: Raw mesh data
        """
        try:
            response = self.client.get_object(self.bucket_name, path)
            data = response.read()
            logger.info(f"Downloaded mesh data: {path}")
            return data
        except S3Error as e:
            logger.error(f"Error downloading mesh data from {path}: {e}")
            raise

    def download_snapshot(self, path: str) -> bytes:
        """
        Download full blend file snapshot.
        
        Args:
            path: Storage path to the snapshot
            
        Returns:
            bytes: Full blend file data
        """
        try:
            response = self.client.get_object(self.bucket_name, path)
            data = response.read()
            logger.info(f"Downloaded snapshot: {path}")
            return data
        except S3Error as e:
            logger.error(f"Error downloading snapshot from {path}: {e}")
            raise

    # ============== Deduplication Methods ==============

    def compute_blob_hash(self, data: Union[Dict[str, Any], bytes]) -> str:
        """
        Compute SHA256 hash for deduplication.
        
        Args:
            data: Dictionary (will be serialized) or raw bytes
            
        Returns:
            str: Hex-encoded SHA256 hash
        """
        if isinstance(data, dict):
            data_bytes = json.dumps(data, sort_keys=True).encode('utf-8')
        else:
            data_bytes = data
        
        return hashlib.sha256(data_bytes).hexdigest()

    def object_exists(self, path: str) -> bool:
        """
        Check if an object exists in storage.
        
        Args:
            path: Storage path to check
            
        Returns:
            bool: True if object exists
        """
        try:
            self.client.stat_object(self.bucket_name, path)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"Error checking object existence at {path}: {e}")
            raise

    def get_object_size(self, path: str) -> int:
        """
        Get the size of an object in bytes.
        
        Args:
            path: Storage path
            
        Returns:
            int: Object size in bytes
        """
        try:
            stat = self.client.stat_object(self.bucket_name, path)
            return stat.size
        except S3Error as e:
            logger.error(f"Error getting object size for {path}: {e}")
            raise

    # ============== Batch Operations ==============

    def list_project_versions(self, project_id: UUID) -> list:
        """
        List all version snapshots for a project.
        
        Args:
            project_id: Project UUID
            
        Returns:
            list: List of version file metadata
        """
        prefix = f"{self._get_project_prefix(project_id)}/versions/"
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix)
            return [obj for obj in objects]
        except S3Error as e:
            logger.error(f"Error listing project versions: {e}")
            raise

    def list_project_objects(self, project_id: UUID) -> list:
        """
        List all object files for a project.
        
        Args:
            project_id: Project UUID
            
        Returns:
            list: List of object file metadata
        """
        prefix = f"{self._get_project_prefix(project_id)}/objects/"
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            return [obj for obj in objects]
        except S3Error as e:
            logger.error(f"Error listing project objects: {e}")
            raise

    def delete_object(self, path: str) -> None:
        """
        Delete a single object from storage.
        
        Args:
            path: Storage path to delete
        """
        try:
            self.client.remove_object(self.bucket_name, path)
            logger.info(f"Deleted object: {path}")
        except S3Error as e:
            logger.error(f"Error deleting object at {path}: {e}")
            raise

    def delete_project_data(self, project_id: UUID) -> None:
        """
        Delete all data associated with a project.
        WARNING: This is irreversible!
        
        Args:
            project_id: Project UUID to delete
        """
        prefix = self._get_project_prefix(project_id)
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            for obj in objects:
                self.client.remove_object(self.bucket_name, obj.object_name)
            logger.warning(f"Deleted all data for project: {project_id}")
        except S3Error as e:
            logger.error(f"Error deleting project data: {e}")
            raise

    # ============== Utility Methods ==============

    def get_object_info(self, path: str) -> Dict[str, Any]:
        """
        Get metadata about a stored object.
        
        Args:
            path: Storage path
            
        Returns:
            dict: Object metadata (size, etag, modified time, etc.)
        """
        try:
            stat = self.client.stat_object(self.bucket_name, path)
            return {
                "name": stat.object_name,
                "size": stat.size,
                "etag": stat.etag,
                "last_modified": stat.last_modified,
                "version_id": stat.version_id,
            }
        except S3Error as e:
            logger.error(f"Error getting object info for {path}: {e}")
            raise

    def estimate_project_storage(self, project_id: UUID) -> Dict[str, int]:
        """
        Calculate storage usage for a project.
        
        Args:
            project_id: Project UUID
            
        Returns:
            dict: Storage breakdown by type (objects, versions, total)
        """
        prefix = self._get_project_prefix(project_id)
        total_size = 0
        objects_size = 0
        versions_size = 0

        try:
            for obj in self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True):
                total_size += obj.size
                if "/objects/" in obj.object_name:
                    objects_size += obj.size
                elif "/versions/" in obj.object_name:
                    versions_size += obj.size

            return {
                "total_bytes": total_size,
                "objects_bytes": objects_size,
                "versions_bytes": versions_size,
                "total_mb": round(total_size / (1024 * 1024), 2),
            }
        except S3Error as e:
            logger.error(f"Error estimating storage for project {project_id}: {e}")
            raise

    def get_presigned_url(self, path: str, expires_hours: int = 1) -> str:
        """
        Generate a presigned URL for temporary access to a file.
        
        Args:
            path: Storage path
            expires_hours: URL expiration time in hours (must be between 1 and MAX_PRESIGNED_URL_HOURS)
            
        Returns:
            str: Presigned URL
            
        Raises:
            ValueError: If expires_hours is invalid
            S3Error: If there's an error generating the URL
        """
        # Validate expires_hours
        if not isinstance(expires_hours, int) or expires_hours < 1 or expires_hours > MAX_PRESIGNED_URL_HOURS:
            raise ValueError(f"expires_hours must be an integer between 1 and {MAX_PRESIGNED_URL_HOURS} (7 days)")
        
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                path,
                expires=timedelta(hours=expires_hours),
            )
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL for {path}: {e}")
            raise

# Global storage service instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """
    Get or create the global storage service instance.
    Used as a FastAPI dependency.
    """
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
