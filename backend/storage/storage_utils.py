"""
Storage Utilities and Helpers

Provides helper functions and utilities for managing storage operations,
file validation, deduplication, and data serialization.
"""

import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from pathlib import Path


class StorageUtils:
    """Utility functions for storage operations"""

    @staticmethod
    def compute_content_hash(data: Dict[str, Any] | bytes) -> str:
        """
        Compute SHA256 hash of content for deduplication.
        
        Args:
            data: Dictionary or bytes to hash
            
        Returns:
            str: Hex-encoded SHA256 hash
        """
        if isinstance(data, dict):
            content = json.dumps(data, sort_keys=True).encode('utf-8')
        else:
            content = data
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def compute_commit_hash(project_id: str, branch_id: str, author_id: str,
                          message: str, timestamp: str) -> str:
        """
        Compute commit hash for versioning.
        
        Similar to Git's commit hashing, combines multiple inputs to create
        a unique identifier for a commit state.
        
        Args:
            project_id: Project UUID
            branch_id: Branch UUID
            author_id: Author UUID
            message: Commit message
            timestamp: Commit timestamp
            
        Returns:
            str: Hex-encoded SHA256 hash
        """
        content = f"{project_id}{branch_id}{author_id}{message}{timestamp}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def validate_object_type(object_type: str) -> bool:
        """
        Validate Blender object type.
        
        Args:
            object_type: Object type string
            
        Returns:
            bool: True if valid
        """
        valid_types = {
            "MESH", "CURVE", "SURFACE", "META", "FONT",
            "ARMATURE", "LATTICE", "EMPTY",
            "LIGHT", "LIGHT_PROBE",
            "CAMERA",
            "SPEAKER",
            "GREASEPENCIL",
            "COLLECTION"
        }
        return object_type.upper() in valid_types

    @staticmethod
    def parse_storage_path(path: str) -> Dict[str, str]:
        """
        Parse a storage path into components.
        
        Example: projects/{project_id}/objects/{object_id}/{commit_hash}.json
        
        Args:
            path: Storage path
            
        Returns:
            dict: Parsed components
        """
        parts = path.split('/')
        
        if len(parts) < 2:
            raise ValueError(f"Invalid storage path: {path}")
        
        result = {}
        
        if parts[0] == "projects":
            result["project_id"] = parts[1] if len(parts) > 1 else None
            
            if len(parts) > 2:
                if parts[2] == "objects":
                    result["type"] = "object"
                    result["object_id"] = parts[3] if len(parts) > 3 else None
                    result["commit_hash"] = parts[4].replace(".json", "") if len(parts) > 4 else None
                elif parts[2] == "versions":
                    result["type"] = "snapshot"
                    result["filename"] = parts[3] if len(parts) > 3 else None
                elif parts[2] == "dedup":
                    result["type"] = "dedup"
                    result["blob_hash"] = parts[3].replace(".json", "") if len(parts) > 3 else None
        
        return result

    @staticmethod
    def format_file_size(bytes_size: int) -> str:
        """
        Format bytes to human-readable size.
        
        Args:
            bytes_size: Size in bytes
            
        Returns:
            str: Formatted size (KB, MB, GB, etc.)
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"

    @staticmethod
    def validate_json_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate Blender object JSON data structure.
        
        Args:
            data: JSON data to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        required_fields = ["object_name", "object_type"]
        
        if not isinstance(data, dict):
            return False, "Data must be a dictionary"
        
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        if not isinstance(data["object_name"], str):
            return False, "object_name must be a string"
        
        if not StorageUtils.validate_object_type(data["object_type"]):
            return False, f"Invalid object_type: {data['object_type']}"
        
        return True, None

    @staticmethod
    def create_metadata(object_name: str, object_type: str, 
                       **kwargs) -> Dict[str, Any]:
        """
        Create standard metadata structure for a Blender object.
        
        Args:
            object_name: Name of the object
            object_type: Type of object
            **kwargs: Additional metadata fields
            
        Returns:
            dict: Metadata structure
        """
        return {
            "object_name": object_name,
            "object_type": object_type,
            "metadata": kwargs
        }


class DeduplicationManager:
    """Manages content deduplication for storage efficiency"""

    def __init__(self, storage_service):
        """
        Initialize deduplication manager.
        
        Args:
            storage_service: StorageService instance
        """
        self.storage = storage_service
        self._hash_index: Dict[str, str] = {}  # blob_hash -> storage_path

    def should_store_separately(self, blob_hash: str) -> bool:
        """
        Check if content with this hash already exists.
        
        Args:
            blob_hash: Content hash
            
        Returns:
            bool: True if content is new
        """
        return blob_hash not in self._hash_index

    def register_hash(self, blob_hash: str, storage_path: str) -> None:
        """
        Register a content hash with its storage location.
        
        Args:
            blob_hash: Content hash
            storage_path: Path in storage
        """
        self._hash_index[blob_hash] = storage_path

    def get_duplicate_path(self, blob_hash: str) -> Optional[str]:
        """
        Get storage path for duplicate content.
        
        Args:
            blob_hash: Content hash
            
        Returns:
            str: Storage path or None if not found
        """
        return self._hash_index.get(blob_hash)

    def calculate_savings(self, total_size: int, actual_stored: int) -> Dict[str, Any]:
        """
        Calculate deduplication savings.
        
        Args:
            total_size: Total content size before deduplication
            actual_stored: Actual size stored
            
        Returns:
            dict: Savings statistics
        """
        saved = total_size - actual_stored
        savings_percent = (saved / total_size * 100) if total_size > 0 else 0
        
        return {
            "total_size": total_size,
            "actual_stored": actual_stored,
            "bytes_saved": saved,
            "percent_saved": round(savings_percent, 2),
        }


class VersioningHelper:
    """Helper functions for version management"""

    @staticmethod
    def create_version_tag(commit_hash: str, timestamp_str: str) -> str:
        """
        Create a human-readable version tag.
        
        Args:
            commit_hash: Commit hash (use first 8 chars)
            timestamp_str: Timestamp string
            
        Returns:
            str: Version tag
        """
        return f"v_{timestamp_str}_{commit_hash[:8]}"

    @staticmethod
    def parse_version_tag(tag: str) -> Dict[str, str]:
        """
        Parse a version tag back to components.
        
        Args:
            tag: Version tag
            
        Returns:
            dict: Parsed components
        """
        parts = tag.split('_')
        if len(parts) >= 3:
            return {
                "commit_hash_short": parts[-1],
                "timestamp": '_'.join(parts[1:-1])
            }
        return {}

    @staticmethod
    def get_version_range(start_commit_hash: str, end_commit_hash: str) -> str:
        """
        Create a version range representation.
        
        Args:
            start_commit_hash: Starting commit hash
            end_commit_hash: Ending commit hash
            
        Returns:
            str: Version range (e.g., "abc1234..def5678")
        """
        return f"{start_commit_hash[:8]}..{end_commit_hash[:8]}"


class StorageCompression:
    """Utilities for compressing and managing large files"""

    import gzip
    import tarfile
    from io import BytesIO

    @staticmethod
    def compress_json(data: Dict[str, Any]) -> bytes:
        """
        Compress JSON data using gzip.
        
        Args:
            data: Dictionary to compress
            
        Returns:
            bytes: Compressed data
        """
        json_bytes = json.dumps(data).encode('utf-8')
        compressed = StorageCompression.gzip.compress(json_bytes)
        return compressed

    @staticmethod
    def decompress_json(data: bytes) -> Dict[str, Any]:
        """
        Decompress gzipped JSON data.
        
        Args:
            data: Compressed data
            
        Returns:
            dict: Decompressed dictionary
        """
        decompressed = StorageCompression.gzip.decompress(data)
        return json.loads(decompressed.decode('utf-8'))


# Export utility classes
__all__ = [
    "StorageUtils",
    "DeduplicationManager",
    "VersioningHelper",
    "StorageCompression",
]
