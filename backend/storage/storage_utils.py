"""
Storage Utilities and Helpers

Provides helper functions and utilities for managing storage operations,
file validation, deduplication, and data serialization.
"""

import json
import hashlib
from typing import Dict, Any, Optional, Tuple, Union


class StorageUtils:
    """Utility functions for storage operations"""

    @staticmethod
    def compute_content_hash(data: Union[Dict[str, Any], bytes]) -> str:
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
    def compute_commit_hash(project_id: str, author_id: str,
                          message: str, timestamp: str) -> str:
        """
        Compute commit hash for versioning.
        
        Similar to Git's commit hashing, combines multiple inputs to create
        a unique identifier for a commit state.
        
        Args:
            project_id: Project UUID
            author_id: Author UUID
            message: Commit message
            timestamp: Commit timestamp
            
        Returns:
            str: Hex-encoded SHA256 hash
        """
        content = f"{project_id}{author_id}{message}{timestamp}".encode('utf-8')
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

        Supported:
        - projects/dedup/{blob_hash}.json
        - projects/{project_id}/dedup/{blob_hash}.json
        - projects/{project_id}/objects/{object_id}/{commit_hash}.json
        - projects/{project_id}/versions/{filename}
        """
        parts = path.split("/")

        if len(parts) < 2:
            raise ValueError(f"Invalid storage path: {path}")

        result: Dict[str, str] = {}

        if parts[0] != "projects":
            return result

        # ----------------------------
        # Format A: projects/dedup/{hash}.json
        # ----------------------------
        if parts[1] == "dedup":
            result["type"] = "dedup"
            result["project_id"] = None
            result["blob_hash"] = parts[2].replace(".json", "") if len(parts) > 2 else None
            return result

        # ----------------------------
        # Format B: projects/{project_id}/...
        # ----------------------------
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


__all__ = ["StorageUtils"]
